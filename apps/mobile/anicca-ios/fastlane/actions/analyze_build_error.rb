module Fastlane
  module Actions
    class AnalyzeBuildErrorAction < Action
      def self.run(params)
        log_path = params[:log_path]
        return nil unless log_path && File.exist?(log_path)
        
        log_content = File.read(log_path)
        errors = []
        warnings = []
        
        # Swiftコンパイルエラーのパターンを検出
        error_patterns = {
          missing_import: /error: (?:cannot find|no such module|use of undeclared type) ['"]([^'"]+)['"]/i,
          missing_scope: /error: (?:cannot find|value of type) ['"]([^'"]+)['"] (?:in scope|has no member)/i,
          syntax_error: /error: (?:expected|unexpected|invalid) (?:token|character|expression)/i,
          type_mismatch: /error: (?:cannot convert|cannot assign|type mismatch)/i,
          missing_protocol: /error: (?:type .+ does not conform to protocol|protocol .+ requires)/i,
          duplicate_declaration: /error: (?:invalid redeclaration|duplicate declaration)/i
        }
        
        # エラーを分類
        log_content.scan(/error:.*$/i) do |error_line|
          error_patterns.each do |type, pattern|
            if error_line.match?(pattern)
              match = error_line.match(pattern)
              errors << {
                type: type,
                message: error_line.strip,
                details: match ? match[1] : nil
              }
              break
            end
          end
        end
        
        # ファイル名と行番号を抽出
        errors.each do |error|
          if match = log_content.match(/([^:]+):(\d+):(\d+):.*#{Regexp.escape(error[:message])}/)
            error[:file] = match[1]
            error[:line] = match[2].to_i
            error[:column] = match[3].to_i
          end
        end
        
        {
          errors: errors,
          warnings: warnings,
          has_errors: !errors.empty?
        }
      end
      
      def self.description
        "Analyze build errors from xcodebuild log"
      end
      
      def self.available_options
        [
          FastlaneCore::ConfigItem.new(key: :log_path,
                                       description: "Path to build log file",
                                       optional: false)
        ]
      end
      
      def self.is_supported?(platform)
        [:ios, :mac].include?(platform)
      end
    end
  end
end





