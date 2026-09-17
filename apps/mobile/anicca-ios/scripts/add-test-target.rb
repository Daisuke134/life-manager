#!/usr/bin/env ruby
require 'xcodeproj'

project_path = File.expand_path('../aniccaios.xcodeproj', __dir__)
project = Xcodeproj::Project.open(project_path)

# Check if test target already exists
existing_target = project.targets.find { |t| t.name == 'aniccaiosTests' }
if existing_target
  puts "Test target 'aniccaiosTests' already exists"
  exit 0
end

# Find the main app target
main_target = project.targets.find { |t| t.name == 'aniccaios' }
unless main_target
  puts "Error: Could not find main target 'aniccaios'"
  exit 1
end

# Create test target
test_target = project.new_target(:unit_test_bundle, 'aniccaiosTests', :ios, '17.0')

# Add dependency on main target
test_target.add_dependency(main_target)

# Create test group
tests_group = project.main_group.new_group('aniccaiosTests', 'aniccaiosTests')

# Set build settings
test_target.build_configurations.each do |config|
  config.build_settings['INFOPLIST_FILE'] = 'aniccaiosTests/Info.plist'
  config.build_settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'com.anicca.ios.tests'
  config.build_settings['TEST_HOST'] = '$(BUILT_PRODUCTS_DIR)/aniccaios.app/$(BUNDLE_EXECUTABLE_FOLDER_PATH)/aniccaios'
  config.build_settings['BUNDLE_LOADER'] = '$(TEST_HOST)'
  config.build_settings['CODE_SIGN_STYLE'] = 'Automatic'
  config.build_settings['DEVELOPMENT_TEAM'] = '9HV2TS77KM'
  config.build_settings['SWIFT_VERSION'] = '5.0'
end

project.save

puts "✅ Test target 'aniccaiosTests' created successfully"

