-- Master Catalog Seed Data
USE AgricultureDB;
SET FOREIGN_KEY_CHECKS = 0;

-- agriculture_offices
DELETE FROM `agriculture_offices`;
INSERT INTO `agriculture_offices` (`office_id`, `office_name`, `phone`, `email`, `address`) VALUES (1, 'Krishi Bhavan - Palakkad Central', '0491-2501234', 'kb.palakkad@agri.gov.in', 'Civil Station Complex, Palakkad');
INSERT INTO `agriculture_offices` (`office_id`, `office_name`, `phone`, `email`, `address`) VALUES (2, 'Krishi Bhavan - Alathur', '0492-2223456', 'kb.alathur@agri.gov.in', 'Main Road, Alathur, Palakkad');
INSERT INTO `agriculture_offices` (`office_id`, `office_name`, `phone`, `email`, `address`) VALUES (3, 'Krishi Bhavan - Chittur', '0492-3256789', 'kb.chittur@agri.gov.in', 'Taluk Office Road, Chittur');
INSERT INTO `agriculture_offices` (`office_id`, `office_name`, `phone`, `email`, `address`) VALUES (4, 'Krishi Bhavan - Thrissur Central', '0487-2334455', 'kb.thrissur@agri.gov.in', 'Ayyanthole, Thrissur');

-- panchayaths
DELETE FROM `panchayaths`;
INSERT INTO `panchayaths` (`panchayath_id`, `panchayath_name`, `district`, `office_id`) VALUES (1, 'Pirayiri Gram Panchayath', 'Palakkad', 1);
INSERT INTO `panchayaths` (`panchayath_id`, `panchayath_name`, `district`, `office_id`) VALUES (2, 'Marutharode Gram Panchayath', 'Palakkad', 1);
INSERT INTO `panchayaths` (`panchayath_id`, `panchayath_name`, `district`, `office_id`) VALUES (3, 'Kannadi Gram Panchayath', 'Palakkad', 1);
INSERT INTO `panchayaths` (`panchayath_id`, `panchayath_name`, `district`, `office_id`) VALUES (4, 'Alathur Gram Panchayath', 'Palakkad', 2);
INSERT INTO `panchayaths` (`panchayath_id`, `panchayath_name`, `district`, `office_id`) VALUES (5, 'Kuzhalmannam Gram Panchayath', 'Palakkad', 2);
INSERT INTO `panchayaths` (`panchayath_id`, `panchayath_name`, `district`, `office_id`) VALUES (6, 'Kavassery Gram Panchayath', 'Palakkad', 2);
INSERT INTO `panchayaths` (`panchayath_id`, `panchayath_name`, `district`, `office_id`) VALUES (7, 'Vadakkencherry Gram Panchayath', 'Palakkad', 2);
INSERT INTO `panchayaths` (`panchayath_id`, `panchayath_name`, `district`, `office_id`) VALUES (8, 'Chittur-Thathamangalam', 'Palakkad', 3);
INSERT INTO `panchayaths` (`panchayath_id`, `panchayath_name`, `district`, `office_id`) VALUES (9, 'Pattanchery Gram Panchayath', 'Palakkad', 3);
INSERT INTO `panchayaths` (`panchayath_id`, `panchayath_name`, `district`, `office_id`) VALUES (10, 'Perumatty Gram Panchayath', 'Palakkad', 3);
INSERT INTO `panchayaths` (`panchayath_id`, `panchayath_name`, `district`, `office_id`) VALUES (11, 'Ollur Gram Panchayath', 'Thrissur', 4);
INSERT INTO `panchayaths` (`panchayath_id`, `panchayath_name`, `district`, `office_id`) VALUES (12, 'Nadathara Gram Panchayath', 'Thrissur', 4);
INSERT INTO `panchayaths` (`panchayath_id`, `panchayath_name`, `district`, `office_id`) VALUES (13, 'Puzhakkal Gram Panchayath', 'Thrissur', 4);

-- crops
DELETE FROM `crops`;
INSERT INTO `crops` (`crop_id`, `crop_name`, `crop_category`, `season`, `growth_duration_days`, `expected_yield_per_acre`) VALUES (1, 'Rice', 'Cereal', 'Kharif', 120, '2200.00');
INSERT INTO `crops` (`crop_id`, `crop_name`, `crop_category`, `season`, `growth_duration_days`, `expected_yield_per_acre`) VALUES (2, 'Wheat', 'Cereal', 'Rabi', 120, '1800.00');

-- fertilizers
DELETE FROM `fertilizers`;
INSERT INTO `fertilizers` (`fertilizer_id`, `fertilizer_name`, `fertilizer_type`, `unit`) VALUES (1, 'Urea (46% N)', 'Chemical', 'kg');
INSERT INTO `fertilizers` (`fertilizer_id`, `fertilizer_name`, `fertilizer_type`, `unit`) VALUES (2, 'Factamfos (20:20:0:13)', 'Complex Chemical', 'kg');
INSERT INTO `fertilizers` (`fertilizer_id`, `fertilizer_name`, `fertilizer_type`, `unit`) VALUES (3, 'Muriate of Potash (MOP)', 'Chemical', 'kg');
INSERT INTO `fertilizers` (`fertilizer_id`, `fertilizer_name`, `fertilizer_type`, `unit`) VALUES (4, 'DAP (18:46:0)', 'Chemical', 'kg');
INSERT INTO `fertilizers` (`fertilizer_id`, `fertilizer_name`, `fertilizer_type`, `unit`) VALUES (5, 'Neem Cake Organic Fertilizer', 'Organic', 'kg');
INSERT INTO `fertilizers` (`fertilizer_id`, `fertilizer_name`, `fertilizer_type`, `unit`) VALUES (6, 'Vermicompost', 'Organic', 'kg');

-- labour_types
DELETE FROM `labour_types`;
INSERT INTO `labour_types` (`labour_id`, `labour_name`, `standard_daily_rate`) VALUES (1, 'Land Preparation & Ploughing', '950.00');
INSERT INTO `labour_types` (`labour_id`, `labour_name`, `standard_daily_rate`) VALUES (2, 'Transplanting & Sowing', '850.00');
INSERT INTO `labour_types` (`labour_id`, `labour_name`, `standard_daily_rate`) VALUES (3, 'Weeding & Intercultivation', '800.00');
INSERT INTO `labour_types` (`labour_id`, `labour_name`, `standard_daily_rate`) VALUES (4, 'Fertilizer & Pesticide Application', '900.00');
INSERT INTO `labour_types` (`labour_id`, `labour_name`, `standard_daily_rate`) VALUES (5, 'Harvesting & Threshing', '950.00');

-- rental_types
DELETE FROM `rental_types`;
INSERT INTO `rental_types` (`rental_id`, `rental_name`, `description`) VALUES (1, 'Tractor (45 HP) with Cultivator', 'Heavy mechanized land tillage equipment');
INSERT INTO `rental_types` (`rental_id`, `rental_name`, `description`) VALUES (2, 'Power Tiller', 'Two-wheel tillage machine suitable for paddy wet fields');
INSERT INTO `rental_types` (`rental_id`, `rental_name`, `description`) VALUES (3, 'Combined Harvester', 'Tracked paddy harvesting and threshing machine');
INSERT INTO `rental_types` (`rental_id`, `rental_name`, `description`) VALUES (4, 'Diesel Irrigation Pump Set (5 HP)', 'Centrifugal high flow water pump');

-- energy_types
DELETE FROM `energy_types`;
INSERT INTO `energy_types` (`energy_id`, `energy_name`) VALUES (1, 'Agricultural Grid Electricity');
INSERT INTO `energy_types` (`energy_id`, `energy_name`) VALUES (2, 'Diesel for Pump/Tractor');
INSERT INTO `energy_types` (`energy_id`, `energy_name`) VALUES (3, 'Solar Water Pump Power');

-- subsidies
DELETE FROM `subsidies`;
INSERT INTO `subsidies` (`subsidy_id`, `subsidy_name`, `description`, `amount`, `start_date`, `end_date`, `eligibility_criteria`) VALUES (1, 'Subhiksha Keralam Paddy Assistance', 'Direct financial aid per acre for active paddy cultivation.', '5500.00', '2026-01-01', '2026-12-31', 'Paddy farmers with registered land in Kerala');
INSERT INTO `subsidies` (`subsidy_id`, `subsidy_name`, `description`, `amount`, `start_date`, `end_date`, `eligibility_criteria`) VALUES (2, 'Organic Farming Incentive Scheme', 'Subsidy for adopting organic inputs and vermicomposting.', '8000.00', '2026-04-01', '2027-03-31', 'Certified organic or transitioning crop producers');
INSERT INTO `subsidies` (`subsidy_id`, `subsidy_name`, `description`, `amount`, `start_date`, `end_date`, `eligibility_criteria`) VALUES (3, 'Farm Mechanization Equipment Grant', '50% grant on hiring or procuring approved agricultural machinery.', '15000.00', '2026-01-01', '2026-12-31', 'Small and marginal farmers holding up to 5 acres');
INSERT INTO `subsidies` (`subsidy_id`, `subsidy_name`, `description`, `amount`, `start_date`, `end_date`, `eligibility_criteria`) VALUES (4, 'Micro-Irrigation Drip System Grant', 'Assistance for installation of drip and sprinkler irrigation.', '12000.00', '2026-02-01', '2026-11-30', 'Horticulture crop growers with dependable water source');

SET FOREIGN_KEY_CHECKS = 1;
