-- ====================================================================
-- Nearby Services WebGIS - Complete PostGIS Database Schema
-- ====================================================================

-- 1. Enable PostGIS Extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- 2. Category Reference Table
CREATE TABLE IF NOT EXISTS service_category (
    category_code VARCHAR(50) PRIMARY KEY,
    category_label VARCHAR(100) NOT NULL,
    icon VARCHAR(50) DEFAULT 'marker'
);

-- 3. Subcategory Reference Table
CREATE TABLE IF NOT EXISTS service_subcategory (
    subcategory_code VARCHAR(50) PRIMARY KEY,
    category_code VARCHAR(50) NOT NULL REFERENCES service_category(category_code) ON DELETE CASCADE,
    subcategory_label VARCHAR(100) NOT NULL
);

-- 4. Primary Spatial Service Table
CREATE TABLE IF NOT EXISTS service (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category_code VARCHAR(50) REFERENCES service_category(category_code) ON DELETE SET NULL,
    subcategory_code VARCHAR(50) REFERENCES service_subcategory(subcategory_code) ON DELETE SET NULL,
    address TEXT,
    phone VARCHAR(50),
    opening_hours VARCHAR(100),
    extra_info JSONB,
    geom GEOGRAPHY(Point, 4326) NOT NULL
);

-- 5. Spatial Index (GiST) for ST_DWithin and KNN (<->) Spatial Queries
CREATE INDEX IF NOT EXISTS idx_service_geom ON service USING GIST (geom);

-- 6. Attribute Filtering Indexes
CREATE INDEX IF NOT EXISTS idx_service_category ON service(category_code);
CREATE INDEX IF NOT EXISTS idx_service_subcategory ON service(subcategory_code);

-- ====================================================================
-- Seed Reference Data (Required for Category Navigation UI & API)
-- ====================================================================

-- Insert Primary Categories
INSERT INTO service_category (category_code, category_label, icon) VALUES 
    ('hospital', 'Hospital', 'local_hospital'),
    ('pharmacy', 'Pharmacy', 'local_pharmacy'),
    ('police', 'Police Station', 'local_police'),
    ('atm', 'ATM', 'local_atm'),
    ('school', 'School', 'school'),
    ('fuel', 'Fuel Station', 'local_gas_station'),
    ('park', 'Park', 'park'),
    ('other', 'Other', 'place')
ON CONFLICT (category_code) DO UPDATE 
SET category_label = EXCLUDED.category_label, icon = EXCLUDED.icon;

-- Insert Subcategories
INSERT INTO service_subcategory (subcategory_code, category_code, subcategory_label) VALUES 
    ('govt_hospital', 'hospital', 'Government Hospital'),
    ('private_hospital', 'hospital', 'Private Clinic'),
    ('retail_pharmacy', 'pharmacy', 'Retail Pharmacy'),
    ('police_station', 'police', 'Police Station'),
    ('bank_atm', 'atm', 'ATM'),
    ('bank_branch', 'atm', 'Bank Branch'),
    ('primary_school', 'school', 'Primary School'),
    ('petrol', 'fuel', 'Petrol Pump'),
    ('public_park', 'park', 'Public Park'),
    ('facility', 'other', 'Civic Facility')
ON CONFLICT (subcategory_code) DO UPDATE 
SET subcategory_label = EXCLUDED.subcategory_label, category_code = EXCLUDED.category_code;