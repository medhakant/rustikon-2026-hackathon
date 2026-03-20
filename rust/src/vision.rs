use opencv::{
    core::{self, Mat, Point2f, Size, Vector, Scalar},
    imgproc,
    calib3d,
    objdetect::{ArucoDetector, DetectorParameters, Dictionary},
    prelude::*,
    Result,
};
use std::collections::HashMap;

pub struct MarkerData {
    pub corners: Vector<Point2f>,
    pub center: Point2f,
    pub area: f64,
    pub heading: f64,
}

pub struct VisionSystem {
    corner_ids: Vec<i32>,
    detector: ArucoDetector,
}

impl VisionSystem {
    pub fn new(corner_ids: Vec<i32>) -> Result<Self> {
        let dictionary = opencv::objdetect::get_predefined_dictionary(opencv::objdetect::PredefinedDictionaryType::DICT_4X4_250)?;
        let mut parameters = DetectorParameters::default()?;
        parameters.set_min_marker_perimeter_rate(0.03);
        let detector = ArucoDetector::new(&dictionary, &parameters, opencv::objdetect::RefineParameters::default()?)?;

        Ok(Self {
            corner_ids,
            detector,
        })
    }

    pub fn detect_markers(&mut self, image: &Mat) -> Result<HashMap<i32, MarkerData>> {
        let mut gray = Mat::default();
        imgproc::cvt_color(image, &mut gray, imgproc::COLOR_BGR2GRAY, 0)?;

        let mut contrast_imgs: Vec<Mat> = Vec::new();
        contrast_imgs.push(gray.clone());

        // Alpha-Beta Sweeps
        let alphas = [1.2, 1.5, 2.0, 3.0];
        let betas = [0.0, 10.0, 30.0, 50.0, -20.0];
        for alpha in alphas.iter() {
            for beta in betas.iter() {
                let mut dst = Mat::default();
                gray.convert_to(&mut dst, core::CV_8U, *alpha, *beta)?;
                contrast_imgs.push(dst);
            }
        }

        // CLAHE sweeps
        let cls = [2.0, 4.0, 6.0];
        let tss = [4, 8, 16];
        for cl in cls.iter() {
            for ts in tss.iter() {
                let mut clahe = imgproc::create_clahe(*cl, Size::new(*ts, *ts))?;
                let mut dst = Mat::default();
                clahe.apply(&gray, &mut dst)?;
                contrast_imgs.push(dst);
            }
        }

        // Gamma sweeps
        let gammas = [0.7, 1.5, 2.0];
        for gamma in gammas.iter() {
            let inv_gamma = 1.0 / gamma;
            // Build LUT
            let mut table = Mat::new_rows_cols_with_default(1, 256, core::CV_8U, Scalar::all(0.0))?;
            for i in 0..256 {
                let v = (((i as f64) / 255.0).powf(inv_gamma) * 255.0) as u8;
                *table.at_mut::<u8>(i as i32)? = v;
            }
            let mut dst = Mat::default();
            core::lut(&gray, &table, &mut dst)?;
            contrast_imgs.push(dst);
        }

        let mut results = HashMap::new();

        for c_img in contrast_imgs.iter() {
            let mut corners = Vector::<Vector<Point2f>>::new();
            let mut ids = Vector::<i32>::new();
            let mut rejected = Vector::<Vector<Point2f>>::new();

            self.detector.detect_markers(c_img, &mut corners, &mut ids, &mut rejected)?;

            for i in 0..ids.len() {
                let id_val = ids.get(i)?;
                if !results.contains_key(&id_val) {
                    let c_pts = corners.get(i)?;

                    // compute center
                    let mut sum_x = 0.0;
                    let mut sum_y = 0.0;
                    for j in 0..4 {
                        sum_x += c_pts.get(j)?.x;
                        sum_y += c_pts.get(j)?.y;
                    }
                    let center = Point2f::new(sum_x / 4.0, sum_y / 4.0);

                    // Area
                    let area = imgproc::contour_area(&c_pts, false)?;

                    // Heading
                    let p0 = c_pts.get(0)?;
                    let p1 = c_pts.get(1)?;
                    let mid_top = Point2f::new((p0.x + p1.x) / 2.0, (p0.y + p1.y) / 2.0);
                    let forward_vec_x = mid_top.x - center.x;
                    let forward_vec_y = mid_top.y - center.y;
                    let heading = (forward_vec_y as f64).atan2(forward_vec_x as f64);

                    results.insert(id_val, MarkerData {
                        corners: c_pts,
                        center,
                        area,
                        heading,
                    });
                }
            }
        }

        Ok(results)
    }

    pub fn compute_homography(&self, detected_markers: &HashMap<i32, MarkerData>) -> Result<Option<Mat>> {
        let mut src_points = Vector::<Point2f>::new();
        
        let mut dst_points = Vector::<Point2f>::new();
        dst_points.push(Point2f::new(0.0, 0.0));
        dst_points.push(Point2f::new(1.0, 0.0));
        dst_points.push(Point2f::new(1.0, 1.0));
        dst_points.push(Point2f::new(0.0, 1.0));

        for c_id in &self.corner_ids {
            if let Some(marker) = detected_markers.get(c_id) {
                src_points.push(marker.center);
            } else {
                return Ok(None);
            }
        }

        let h = calib3d::get_perspective_transform(&src_points, &dst_points, calib3d::DECOMP_LU)?;
        Ok(Some(h))
    }

    pub fn get_car_pose(
        &mut self,
        image1: Option<&Mat>,
        image2: Option<&Mat>,
        car_id: i32,
        h1: Option<&Mat>,
        h2: Option<&Mat>,
    ) -> Result<Option<(Point2f, f64)>> {
        let res1 = if let Some(img1) = image1 { self.detect_markers(img1)? } else { HashMap::new() };
        let res2 = if let Some(img2) = image2 { self.detect_markers(img2)? } else { HashMap::new() };

        let mut poses = Vec::new();
        let mut areas = Vec::new();

        let process_pose = |res: &HashMap<i32, MarkerData>, h_opt: Option<&Mat>| -> Result<Option<(Point2f, f64, f64)>> {
            if let (Some(m), Some(h)) = (res.get(&car_id), h_opt) {
                let mut center_vec = Vector::<Point2f>::new();
                center_vec.push(m.center);
                let mut center_t = Vector::<Point2f>::new();
                core::perspective_transform(&center_vec, &mut center_t, h)?;

                let forward_pt = Point2f::new(
                    m.center.x + m.heading.cos() as f32,
                    m.center.y + m.heading.sin() as f32,
                );
                let mut forward_vec = Vector::<Point2f>::new();
                forward_vec.push(forward_pt);
                let mut forward_t = Vector::<Point2f>::new();
                core::perspective_transform(&forward_vec, &mut forward_t, h)?;

                let ct = center_t.get(0)?;
                let ft = forward_t.get(0)?;

                let heading_t = (ft.y - ct.y).atan2(ft.x - ct.x) as f64;
                Ok(Some((ct, heading_t, m.area)))
            } else {
                Ok(None)
            }
        };

        if let Some((ct, ht, area)) = process_pose(&res1, h1)? {
            poses.push((ct, ht));
            areas.push(area);
        }

        if let Some((ct, ht, area)) = process_pose(&res2, h2)? {
            poses.push((ct, ht));
            areas.push(area);
        }

        if poses.is_empty() {
            return Ok(None);
        }

        if poses.len() == 1 {
            let (pt, hdg) = poses[0];
            return Ok(Some((pt, hdg)));
        }

        let total_area: f64 = areas.iter().sum();
        let w1 = areas[0] / total_area;
        let w2 = areas[1] / total_area;

        let avg_x = (poses[0].0.x as f64) * w1 + (poses[1].0.x as f64) * w2;
        let avg_y = (poses[0].0.y as f64) * w1 + (poses[1].0.y as f64) * w2;

        let x_dir = poses[0].1.cos() * w1 + poses[1].1.cos() * w2;
        let y_dir = poses[0].1.sin() * w1 + poses[1].1.sin() * w2;
        let avg_heading = y_dir.atan2(x_dir);

        Ok(Some((Point2f::new(avg_x as f32, avg_y as f32), avg_heading)))
    }
}
