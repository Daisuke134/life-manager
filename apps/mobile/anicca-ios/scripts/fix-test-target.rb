#!/usr/bin/env ruby
require 'xcodeproj'

project_path = File.expand_path('../aniccaios.xcodeproj', __dir__)
project = Xcodeproj::Project.open(project_path)

# Find test target
test_target = project.targets.find { |t| t.name == 'aniccaiosTests' }
unless test_target
  puts "Error: Could not find test target 'aniccaiosTests'"
  exit 1
end

# Fix build settings
test_target.build_configurations.each do |config|
  config.build_settings['PRODUCT_NAME'] = 'aniccaiosTests'
  config.build_settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'com.anicca.ios.tests'
  config.build_settings['INFOPLIST_FILE'] = 'aniccaiosTests/Info.plist'
  config.build_settings['TEST_HOST'] = '$(BUILT_PRODUCTS_DIR)/aniccaios.app/$(BUNDLE_EXECUTABLE_FOLDER_PATH)/aniccaios'
  config.build_settings['BUNDLE_LOADER'] = '$(TEST_HOST)'
  config.build_settings['CODE_SIGN_STYLE'] = 'Automatic'
  config.build_settings['DEVELOPMENT_TEAM'] = '9HV2TS77KM'
  config.build_settings['SWIFT_VERSION'] = '5.0'
  config.build_settings['IPHONEOS_DEPLOYMENT_TARGET'] = '17.0'
  config.build_settings['GENERATE_INFOPLIST_FILE'] = 'YES'
  puts "Fixed config: #{config.name}"
end

project.save
puts "✅ Test target fixed successfully"

