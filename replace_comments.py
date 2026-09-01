#!/usr/bin/env python3
"""Replace English comments with Hinglish comments."""

# Daily risk forecast
print("Updating: heat_health/daily_risk_forecast.py")
with open('heat_health/daily_risk_forecast.py', 'r', encoding='utf-8') as f:
    content = f.read()

replacements = [
    ('# Screening score breakpoints.', '# Screening score ke breakpoints.'),
    ('# Thermal hazard is the main factor.', '# Thermal hazard main factor hai.'),
    ('# Population exposure and duration amplify that hazard.', '# Population exposure aur duration se hazard badhta hai.'),
    ('# Validate input files', '# Input files validate karo'),
    ('# Read inputs', '# Inputs padho'),
    ('# Validate and prepare hourly data', '# Hourly data ko validate aur prepare karo'),
    ('# Calculate thermal hazard score', '# Thermal hazard score nikalo'),
    ('# Confirm 24 hours exist for every ward/day', '# Har ward/day ke liye 24 hours hain confirm karo'),
    ('# Daily aggregation', '# Daily data ko combine karo'),
    ('# Night-time temperature', '# Raat ka temperature'),
    ('# Peak-risk forecast time', '# Sabse zyada risky waqt'),
    ('# Join population exposure', '# Population exposure ko jodo'),
    ('# Calculate duration and persistence', '# Duration aur persistence nikalo'),
    ('# Provisional Mortality Risk Index', '# Azmayishi Mortality Risk Index'),
]

for old, new in replacements:
    content = content.replace(old, new)

with open('heat_health/daily_risk_forecast.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("✓ Updated: heat_health/daily_risk_forecast.py")

# Daily features
print("Updating: heat_health/daily_features.py")
with open('heat_health/daily_features.py', 'r', encoding='utf-8') as f:
    content = f.read()

replacements = [
    ('# Parse timestamp and ensure it uses Indian Standard Time.', '# Timestamp ko parse karo aur Indian Standard Time use karo.'),
    ('# A dangerous hour occurs when either index enters a high-risk range.', '# Khatarnak ghanta jab koi bhi index high-risk mein jaaye.'),
    ('# Nighttime is defined here as 10 PM through 6 AM.', '# Raat 10 PM se 6 AM tak hoti hai.'),
    ('# Calculate minimum nighttime temperature separately.', '# Raat ka minimum temperature alag se nikalo.'),
]

for old, new in replacements:
    content = content.replace(old, new)

with open('heat_health/daily_features.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("✓ Updated: heat_health/daily_features.py")

# Mortality calibration
print("Updating: heat_health/mortality_calibration.py")
with open('heat_health/mortality_calibration.py', 'r', encoding='utf-8') as f:
    content = f.read()

replacements = [
    ('# File locations', '# File ki locations'),
    ('# Published Indian multi-city study coefficients.', '# Published Indian multi-city study ke coefficients.'),
    ('# Utility functions', '# Helper functions'),
    ('# Evidence-based mortality calibration', '# Evidence se based mortality calibration'),
    ('# Operational definition of severe physiological heat.', '# Severe heat ka operational definition.'),
    ('# Five-day severe heat proxy.', '# Paanch din ka severe heat proxy.'),
    ('# Published two-consecutive-day heatwave relationship.', '# Published do-consecutive-din heatwave ka relationship.'),
]

for old, new in replacements:
    content = content.replace(old, new)

with open('heat_health/mortality_calibration.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("✓ Updated: heat_health/mortality_calibration.py")

# Population exposure
print("Updating: heat_health/population_exposure.py")
with open('heat_health/population_exposure.py', 'r', encoding='utf-8') as f:
    content = f.read()

replacements = [
    ('# File paths', '# File ke paths'),
    ('# Processing settings', '# Processing ke settings'),
    ('# Validate files', '# Files ko validate karo'),
    ('# Read ward polygons', '# Ward polygons padho'),
    ('# Prepare population density grid', '# Population density grid prepare karo'),
    ('# Calculate population inside every ward', '# Har ward ke andar population nikalo'),
    ('# Create population features', '# Population features banao'),
    ('# Create exposure scores', '# Exposure scores banao'),
    ('Convert values into scores between 0 and 100.', 'Values ko 0 aur 100 ke beech scores mein convert karo.'),
    ('The 5th and 95th percentiles are used to reduce the', '5th aur 95th percentiles use karke'),
    ('influence of unusually small or large wards.', 'unusual chote ya bade wards ka influence kam karo.'),
    ('Crop the India WorldPop raster to Delhi and reproject', 'India WorldPop raster ko Delhi tak crop karo aur reproject'),
    ('it to a 100-metre Delhi calculation grid.', 'ise 100-metre Delhi calculation grid mein.'),
    ('Estimate population and population exposure for every', 'Har Delhi ward ke liye population aur population exposure'),
    ('Delhi ward.', 'estimate karo.'),
]

for old, new in replacements:
    content = content.replace(old, new)

with open('heat_health/population_exposure.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("✓ Updated: heat_health/population_exposure.py")

# Spatial setup
print("Updating: heat_health/spatial_setup.py")
with open('heat_health/spatial_setup.py', 'r', encoding='utf-8') as f:
    content = f.read()

replacements = [
    ('# Input and output paths', '# Input aur output paths'),
    ('# Dataset metadata', '# Dataset ki metadata'),
    ('Convert missing values to an empty string and remove', 'Missing values ko empty string mein convert karo aur'),
    ('unnecessary spaces from existing text values.', 'text values se unnecessary spaces hatao.'),
    ('Read, validate and process Delhi ward boundaries.', 'Delhi ward boundaries ko padho, validate karo aur process karo.'),
    ('# Check input file', '# Input file check karo'),
    ('# Read GeoJSON', '# GeoJSON padho'),
    ('# Validate required columns', '# Required columns validate karo'),
    ('# Validate geometry', '# Geometry validate karo'),
    ('# Clean ward IDs and ward names', '# Ward IDs aur ward names ko saaf karo'),
    ('# Handle missing Ward_No', '# Missing Ward_No ko handle karo'),
    ('# Handle missing Ward_Name', '# Missing Ward_Name ko handle karo'),
    ('# Rename columns to project-standard names', '# Columns ko project-standard names mein rename karo'),
    ('# Confirm ward IDs are unique', '# Ward IDs unique hain confirm karo'),
    ('# Set coordinate reference system', '# Coordinate reference system set karo'),
    ('# Repair invalid geometries, if present', '# Invalid geometries ko repair karo'),
    ('# Calculate ward areas', '# Ward areas calculate karo'),
    ('# Calculate ward centroids', '# Ward centroids calculate karo'),
    ('# EPSG:32643 is UTM Zone 43N, suitable for Delhi.', '# EPSG:32643 UTM Zone 43N hai, Delhi ke liye theek hai.'),
    ('# Geographic coordinates cannot calculate area correctly,', '# Geographic coordinates se area sahi se calculate nahi ho sakta,'),
    ('# so geometry is temporarily projected.', '# isliye geometry ko temporary project karte hain.'),
]

for old, new in replacements:
    content = content.replace(old, new)

with open('heat_health/spatial_setup.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("✓ Updated: heat_health/spatial_setup.py")

# Thermal
print("Updating: heat_health/thermal.py")
with open('heat_health/thermal.py', 'r', encoding='utf-8') as f:
    content = f.read()

replacements = [
    ('# Avoid physically unrealistic values from abnormal weather inputs.', '# Abnormal weather inputs se unrealistic values avoid karo.'),
    ('Validate weather inputs before calculations.', 'Calculations se pehle weather inputs ko validate karo.'),
    ('Estimate wet-bulb temperature using the Stull approximation.', 'Stull approximation se wet-bulb temperature estimate karo.'),
    ('Estimate black-globe temperature.', 'Black-globe temperature estimate karo.'),
    ('Solar radiation raises globe temperature, while wind provides cooling.', 'Solar radiation se globe temperature badhta hai, hawa se thandi hoti hai.'),
    ('This is a screening approximation, not a physical globe-thermometer', 'Yeh screening approximation hai, globe-thermometer nahi'),
    ('measurement.', 'measurement.'),
    ('Estimate mean radiant temperature from globe temperature.', 'Globe temperature se mean radiant temperature estimate karo.'),
    ('Classify overall human thermal stress.', 'Overall human thermal stress ko classify karo.'),
    ('Calculate all thermal-stress indices for one weather observation.', 'Ek weather observation ke liye sab thermal-stress indices calculate karo.'),
    ('# 1. Heat Index', '# 1. Heat Index nikalo'),
    ('# 2. Wet-bulb temperature', '# 2. Wet-bulb temperature nikalo'),
    ('# 3. Globe temperature', '# 3. Globe temperature nikalo'),
    ('# 4. Mean radiant temperature', '# 4. Mean radiant temperature nikalo'),
    ('# 5. WBGT', '# 5. WBGT nikalo'),
    ('# 6. UTCI', '# 6. UTCI nikalo'),
    ('# 7. Wet-bulb WBGT if solar radiation is significant', '# 7. Agar solar radiation zyada hai toh Wet-bulb WBGT nikalo'),
]

for old, new in replacements:
    content = content.replace(old, new)

with open('heat_health/thermal.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("✓ Updated: heat_health/thermal.py")

# WardMap JSX
print("Updating: frontend/src/components/WardMap.jsx")
with open('frontend/src/components/WardMap.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

replacements = [
    ('Continuous intensity colours make differences visible while preserving', 'Rang intensity se farak dikta hai aur'),
    ('the official High/Extreme risk level shown in the ward information.', 'official risk level ward information mein dikhta hai.'),
]

for old, new in replacements:
    content = content.replace(old, new)

with open('frontend/src/components/WardMap.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print("✓ Updated: frontend/src/components/WardMap.jsx")

print("\n✅ All files updated successfully!")
