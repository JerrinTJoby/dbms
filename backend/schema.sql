-- =====================================================
-- AGRICULTURE MANAGEMENT SYSTEM
-- Database: AgricultureDB
-- =====================================================

CREATE DATABASE IF NOT EXISTS AgricultureDB;
USE AgricultureDB;

-- 1. USERS (Minimal Registration)
CREATE TABLE Users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('FARMER', 'OFFICER') NOT NULL,
    full_name VARCHAR(100) NULL,
    phone VARCHAR(15) NULL,
    is_profile_complete BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. AGRICULTURE OFFICES (e.g., Krishi Bhavans)
CREATE TABLE Agriculture_Offices (
    office_id INT AUTO_INCREMENT PRIMARY KEY,
    office_name VARCHAR(150) NOT NULL,
    phone VARCHAR(15),
    email VARCHAR(150),
    address VARCHAR(255)
);

-- 3. PANCHAYATHS (Gram Panchayaths linked to Offices)
CREATE TABLE Panchayaths (
    panchayath_id INT AUTO_INCREMENT PRIMARY KEY,
    panchayath_name VARCHAR(150) NOT NULL,
    district VARCHAR(100) NOT NULL,
    office_id INT NOT NULL,
    FOREIGN KEY (office_id) REFERENCES Agriculture_Offices(office_id) ON DELETE RESTRICT
);

-- 4. AGRICULTURAL OFFICERS
CREATE TABLE Officers (
    officer_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    office_id INT NOT NULL,
    panchayath_id INT NULL,
    designation VARCHAR(100) DEFAULT 'Agricultural Officer',
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (office_id) REFERENCES Agriculture_Offices(office_id) ON DELETE RESTRICT,
    FOREIGN KEY (panchayath_id) REFERENCES Panchayaths(panchayath_id) ON DELETE SET NULL
);

-- 5. FARMERS
CREATE TABLE Farmers (
    farmer_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    panchayath_id INT NOT NULL,
    address VARCHAR(255),
    registration_date DATE DEFAULT (CURRENT_DATE),
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (panchayath_id) REFERENCES Panchayaths(panchayath_id) ON DELETE RESTRICT
);

-- 6. FARMS
CREATE TABLE Farms (
    farm_id INT AUTO_INCREMENT PRIMARY KEY,
    farmer_id INT NOT NULL,
    farm_name VARCHAR(100),
    location VARCHAR(255) NOT NULL,
    area_acres DECIMAL(10,2) NOT NULL,
    soil_type VARCHAR(50),
    irrigation_type VARCHAR(50),
    FOREIGN KEY (farmer_id) REFERENCES Farmers(farmer_id) ON DELETE CASCADE,
    CHECK (area_acres > 0)
);

-- 7. CROPS
CREATE TABLE Crops (
    crop_id INT AUTO_INCREMENT PRIMARY KEY,
    crop_name VARCHAR(100) NOT NULL UNIQUE,
    crop_category VARCHAR(50),
    season VARCHAR(50),
    growth_duration_days INT,
    expected_yield_per_acre DECIMAL(10,2),
    CHECK (growth_duration_days IS NULL OR growth_duration_days > 0),
    CHECK (expected_yield_per_acre IS NULL OR expected_yield_per_acre >= 0)
);

-- 8. FARM CROPS
CREATE TABLE Farm_Crops (
    farm_crop_id INT AUTO_INCREMENT PRIMARY KEY,
    farm_id INT NOT NULL,
    crop_id INT NOT NULL,
    season VARCHAR(50),
    planting_date DATE,
    expected_harvest_date DATE,
    actual_harvest_date DATE,
    cultivated_area_acres DECIMAL(10,2) NOT NULL,
    status ENUM('PLANNED', 'GROWING', 'HARVESTED', 'FAILED') DEFAULT 'PLANNED',
    FOREIGN KEY (farm_id) REFERENCES Farms(farm_id) ON DELETE CASCADE,
    FOREIGN KEY (crop_id) REFERENCES Crops(crop_id) ON DELETE RESTRICT,
    CHECK (cultivated_area_acres > 0)
);

-- 9. LABOUR TYPES
CREATE TABLE Labour_Types (
    labour_id INT AUTO_INCREMENT PRIMARY KEY,
    labour_name VARCHAR(100) NOT NULL UNIQUE,
    standard_daily_rate DECIMAL(10,2)
);

-- 10. FERTILIZERS
CREATE TABLE Fertilizers (
    fertilizer_id INT AUTO_INCREMENT PRIMARY KEY,
    fertilizer_name VARCHAR(120) NOT NULL UNIQUE,
    fertilizer_type VARCHAR(50),
    unit VARCHAR(20) DEFAULT 'kg'
);

-- 11. RENTAL TYPES
CREATE TABLE Rental_Types (
    rental_id INT AUTO_INCREMENT PRIMARY KEY,
    rental_name VARCHAR(120) NOT NULL UNIQUE,
    description VARCHAR(255)
);

-- 12. ENERGY TYPES
CREATE TABLE Energy_Types (
    energy_id INT AUTO_INCREMENT PRIMARY KEY,
    energy_name VARCHAR(100) NOT NULL UNIQUE
);

-- 13. EXPENSES
CREATE TABLE Expenses (
    expense_id INT AUTO_INCREMENT PRIMARY KEY,
    farm_id INT NOT NULL,
    farm_crop_id INT NULL,
    expense_category ENUM('SEEDS', 'RENTAL', 'ENERGY', 'IRRIGATION', 'TRANSPORT', 'OTHER') NOT NULL,
    rental_id INT NULL,
    energy_id INT NULL,
    amount DECIMAL(12,2) NOT NULL,
    expense_date DATE NOT NULL,
    description VARCHAR(255),
    FOREIGN KEY (farm_id) REFERENCES Farms(farm_id) ON DELETE CASCADE,
    FOREIGN KEY (farm_crop_id) REFERENCES Farm_Crops(farm_crop_id) ON DELETE SET NULL,
    FOREIGN KEY (rental_id) REFERENCES Rental_Types(rental_id) ON DELETE SET NULL,
    FOREIGN KEY (energy_id) REFERENCES Energy_Types(energy_id) ON DELETE SET NULL
);

-- 14. FARM CROP LABOUR
CREATE TABLE Farm_Crop_Labour (
    labour_usage_id INT AUTO_INCREMENT PRIMARY KEY,
    farm_crop_id INT NOT NULL,
    labour_id INT NOT NULL,
    work_date DATE NOT NULL,
    worker_count INT NOT NULL DEFAULT 1,
    days_worked DECIMAL(6,2) NOT NULL DEFAULT 1,
    total_cost DECIMAL(12,2) NOT NULL,
    FOREIGN KEY (farm_crop_id) REFERENCES Farm_Crops(farm_crop_id) ON DELETE CASCADE,
    FOREIGN KEY (labour_id) REFERENCES Labour_Types(labour_id) ON DELETE RESTRICT
);

-- 15. FARM CROP FERTILIZER
CREATE TABLE Farm_Crop_Fertilizer (
    application_id INT AUTO_INCREMENT PRIMARY KEY,
    farm_crop_id INT NOT NULL,
    fertilizer_id INT NOT NULL,
    application_date DATE NOT NULL,
    quantity DECIMAL(12,2) NOT NULL,
    total_cost DECIMAL(12,2) NOT NULL DEFAULT 0,
    FOREIGN KEY (farm_crop_id) REFERENCES Farm_Crops(farm_crop_id) ON DELETE CASCADE,
    FOREIGN KEY (fertilizer_id) REFERENCES Fertilizers(fertilizer_id) ON DELETE RESTRICT
);

-- 16. INCOME
CREATE TABLE Income (
    income_id INT AUTO_INCREMENT PRIMARY KEY,
    farm_crop_id INT NOT NULL,
    sale_date DATE NOT NULL,
    quantity_sold DECIMAL(12,2) NOT NULL,
    unit VARCHAR(20) DEFAULT 'kg',
    price_per_unit DECIMAL(12,2) NOT NULL,
    total_income DECIMAL(14,2) GENERATED ALWAYS AS (quantity_sold * price_per_unit) STORED,
    buyer_name VARCHAR(150),
    FOREIGN KEY (farm_crop_id) REFERENCES Farm_Crops(farm_crop_id) ON DELETE CASCADE
);

-- 17. SUBSIDIES
CREATE TABLE Subsidies (
    subsidy_id INT AUTO_INCREMENT PRIMARY KEY,
    subsidy_name VARCHAR(150) NOT NULL,
    description TEXT,
    amount DECIMAL(12,2) NOT NULL,
    start_date DATE,
    end_date DATE,
    eligibility_criteria TEXT
);

-- 18. FARMER SUBSIDIES
CREATE TABLE Farmer_Subsidies (
    farmer_subsidy_id INT AUTO_INCREMENT PRIMARY KEY,
    farmer_id INT NOT NULL,
    subsidy_id INT NOT NULL,
    officer_id INT NULL,
    application_date DATE NOT NULL,
    status ENUM('PENDING', 'APPROVED', 'REJECTED', 'PAID') DEFAULT 'PENDING',
    approved_amount DECIMAL(12,2),
    payment_date DATE,
    remarks VARCHAR(255),
    FOREIGN KEY (farmer_id) REFERENCES Farmers(farmer_id) ON DELETE CASCADE,
    FOREIGN KEY (subsidy_id) REFERENCES Subsidies(subsidy_id) ON DELETE RESTRICT,
    FOREIGN KEY (officer_id) REFERENCES Officers(officer_id) ON DELETE SET NULL,
    UNIQUE (farmer_id, subsidy_id)
);

-- =====================================================
-- VIEW FOR OFFICER DIRECTORY
-- =====================================================
CREATE VIEW Officer_Farmer_Directory AS
SELECT 
    off.office_id,
    off.office_name,
    o.officer_id,
    u_off.user_id AS officer_user_id,
    u_off.full_name AS officer_name,
    p.panchayath_id,
    p.panchayath_name,
    p.district,
    f.farmer_id,
    u_farm.full_name AS farmer_name,
    u_farm.email AS farmer_email,
    u_farm.phone AS farmer_phone,
    f.address AS farmer_address,
    f.registration_date
FROM Officers o
JOIN Users u_off ON o.user_id = u_off.user_id
JOIN Agriculture_Offices off ON o.office_id = off.office_id
JOIN Panchayaths p ON off.office_id = p.office_id
JOIN Farmers f ON p.panchayath_id = f.panchayath_id
JOIN Users u_farm ON f.user_id = u_farm.user_id;