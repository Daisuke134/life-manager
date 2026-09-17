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

# Find or create tests group
tests_group = project.main_group.find_subpath('aniccaiosTests', true)
tests_group.set_source_tree('<group>')
tests_group.set_path('aniccaiosTests')

# Test files to add
test_files = [
  'BetaDistributionTests.swift',
  'NudgeContentSelectorTests.swift',
  'NudgeStatsManagerTests.swift',
  'Info.plist'
]

test_files.each do |filename|
  file_path = File.expand_path("../aniccaiosTests/#{filename}", __dir__)
  
  # Check if file already exists in project
  existing = tests_group.files.find { |f| f.name == filename || f.path == filename }
  if existing
    puts "File already in project: #{filename}"
    next
  end
  
  # Add file to group
  file_ref = tests_group.new_file(filename)
  
  # Add to target's sources phase (except Info.plist)
  unless filename.end_with?('.plist')
    test_target.source_build_phase.add_file_reference(file_ref)
    puts "Added to sources: #{filename}"
  else
    puts "Added Info.plist: #{filename}"
  end
end

project.save
puts "✅ Test files added successfully"

