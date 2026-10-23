require "minitest/autorun"

# Execute the real lane while replacing Fastlane's external actions.
class ReviewLane
  attr_reader :lanes, :submission

  def initialize
    @lanes = {}
  end

  def default_platform(*) = nil
  def platform(*) = yield
  def desc(*) = nil
  def lane(name, &block) = @lanes[name] = block
  def app_store_connect_api_key(*) = :test_key
  def latest_testflight_build_number(*) = 390
  def get_version_number(*) = "1.9.6"
  def deliver(**options) = @submission = options
  def notification(*) = nil
end

module UI
  def self.important(*) = nil
  def self.success(*) = nil
end

class SubmitReviewTest < Minitest::Test
  def test_explicit_version_and_build_reach_submission
    runner = ReviewLane.new
    runner.instance_eval(File.read(File.expand_path("../../fastlane/Fastfile", __dir__)))
    runner.lanes.fetch(:submit_review).call(version: "2.0.0", build_number: 999)

    assert_equal "2.0.0", runner.submission[:app_version]
    assert_equal "999", runner.submission[:build_number]
  end

  def test_default_version_and_build_reach_submission
    runner = ReviewLane.new
    runner.instance_eval(File.read(File.expand_path("../../fastlane/Fastfile", __dir__)))
    runner.lanes.fetch(:submit_review).call({})

    assert_equal "1.9.6", runner.submission[:app_version]
    assert_equal "390", runner.submission[:build_number]
  end
end
