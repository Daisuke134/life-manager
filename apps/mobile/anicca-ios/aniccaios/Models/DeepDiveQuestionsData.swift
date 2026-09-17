import Foundation

/// 深掘り質問のデータ構造
struct DeepDiveQuestion {
    let questionKey: String
    let optionKeys: [String]
}

/// 深掘り質問データ
enum DeepDiveQuestionsData {
    /// 共通質問: どのくらい前からこの問題がある？
    static let commonDurationQuestion = DeepDiveQuestion(
        questionKey: "deepdive_common_duration_question",
        optionKeys: [
            "deepdive_common_duration_recent",
            "deepdive_common_duration_months",
            "deepdive_common_duration_year",
            "deepdive_common_duration_always"
        ]
    )

    /// 各問題の質問データ
    static func questions(for problem: ProblemType) -> [DeepDiveQuestion] {
        switch problem {
        case .stayingUpLate:
            return [
                DeepDiveQuestion(
                    questionKey: "deepdive_staying_up_late_q1",
                    optionKeys: [
                        "deepdive_staying_up_late_q1_opt1",
                        "deepdive_staying_up_late_q1_opt2",
                        "deepdive_staying_up_late_q1_opt3",
                        "deepdive_staying_up_late_q1_opt4",
                        "deepdive_staying_up_late_q1_opt5"
                    ]
                ),
                DeepDiveQuestion(
                    questionKey: "deepdive_staying_up_late_q2",
                    optionKeys: [
                        "deepdive_staying_up_late_q2_opt1",
                        "deepdive_staying_up_late_q2_opt2",
                        "deepdive_staying_up_late_q2_opt3",
                        "deepdive_staying_up_late_q2_opt4"
                    ]
                )
            ]
        case .cantWakeUp:
            return [
                DeepDiveQuestion(
                    questionKey: "deepdive_cant_wake_up_q1",
                    optionKeys: [
                        "deepdive_cant_wake_up_q1_opt1",
                        "deepdive_cant_wake_up_q1_opt2",
                        "deepdive_cant_wake_up_q1_opt3",
                        "deepdive_cant_wake_up_q1_opt4"
                    ]
                ),
                DeepDiveQuestion(
                    questionKey: "deepdive_cant_wake_up_q2",
                    optionKeys: [
                        "deepdive_cant_wake_up_q2_opt1",
                        "deepdive_cant_wake_up_q2_opt2",
                        "deepdive_cant_wake_up_q2_opt3",
                        "deepdive_cant_wake_up_q2_opt4"
                    ]
                )
            ]
        case .selfLoathing:
            return [
                DeepDiveQuestion(
                    questionKey: "deepdive_self_loathing_q1",
                    optionKeys: [
                        "deepdive_self_loathing_q1_opt1",
                        "deepdive_self_loathing_q1_opt2",
                        "deepdive_self_loathing_q1_opt3",
                        "deepdive_self_loathing_q1_opt4"
                    ]
                ),
                DeepDiveQuestion(
                    questionKey: "deepdive_self_loathing_q2",
                    optionKeys: [
                        "deepdive_self_loathing_q2_opt1",
                        "deepdive_self_loathing_q2_opt2",
                        "deepdive_self_loathing_q2_opt3",
                        "deepdive_self_loathing_q2_opt4"
                    ]
                )
            ]
        case .rumination:
            return [
                DeepDiveQuestion(
                    questionKey: "deepdive_rumination_q1",
                    optionKeys: [
                        "deepdive_rumination_q1_opt1",
                        "deepdive_rumination_q1_opt2",
                        "deepdive_rumination_q1_opt3",
                        "deepdive_rumination_q1_opt4"
                    ]
                ),
                DeepDiveQuestion(
                    questionKey: "deepdive_rumination_q2",
                    optionKeys: [
                        "deepdive_rumination_q2_opt1",
                        "deepdive_rumination_q2_opt2",
                        "deepdive_rumination_q2_opt3",
                        "deepdive_rumination_q2_opt4"
                    ]
                )
            ]
        case .procrastination:
            return [
                DeepDiveQuestion(
                    questionKey: "deepdive_procrastination_q1",
                    optionKeys: [
                        "deepdive_procrastination_q1_opt1",
                        "deepdive_procrastination_q1_opt2",
                        "deepdive_procrastination_q1_opt3",
                        "deepdive_procrastination_q1_opt4"
                    ]
                ),
                DeepDiveQuestion(
                    questionKey: "deepdive_procrastination_q2",
                    optionKeys: [
                        "deepdive_procrastination_q2_opt1",
                        "deepdive_procrastination_q2_opt2",
                        "deepdive_procrastination_q2_opt3",
                        "deepdive_procrastination_q2_opt4"
                    ]
                )
            ]
        case .anxiety:
            return [
                DeepDiveQuestion(
                    questionKey: "deepdive_anxiety_q1",
                    optionKeys: [
                        "deepdive_anxiety_q1_opt1",
                        "deepdive_anxiety_q1_opt2",
                        "deepdive_anxiety_q1_opt3",
                        "deepdive_anxiety_q1_opt4"
                    ]
                ),
                DeepDiveQuestion(
                    questionKey: "deepdive_anxiety_q2",
                    optionKeys: [
                        "deepdive_anxiety_q2_opt1",
                        "deepdive_anxiety_q2_opt2",
                        "deepdive_anxiety_q2_opt3",
                        "deepdive_anxiety_q2_opt4"
                    ]
                )
            ]
        case .lying:
            return [
                DeepDiveQuestion(
                    questionKey: "deepdive_lying_q1",
                    optionKeys: [
                        "deepdive_lying_q1_opt1",
                        "deepdive_lying_q1_opt2",
                        "deepdive_lying_q1_opt3",
                        "deepdive_lying_q1_opt4"
                    ]
                ),
                DeepDiveQuestion(
                    questionKey: "deepdive_lying_q2",
                    optionKeys: [
                        "deepdive_lying_q2_opt1",
                        "deepdive_lying_q2_opt2",
                        "deepdive_lying_q2_opt3",
                        "deepdive_lying_q2_opt4"
                    ]
                ),
                DeepDiveQuestion(
                    questionKey: "deepdive_lying_q3",
                    optionKeys: [
                        "deepdive_lying_q3_opt1",
                        "deepdive_lying_q3_opt2",
                        "deepdive_lying_q3_opt3",
                        "deepdive_lying_q3_opt4"
                    ]
                )
            ]
        case .badMouthing:
            return [
                DeepDiveQuestion(
                    questionKey: "deepdive_bad_mouthing_q1",
                    optionKeys: [
                        "deepdive_bad_mouthing_q1_opt1",
                        "deepdive_bad_mouthing_q1_opt2",
                        "deepdive_bad_mouthing_q1_opt3",
                        "deepdive_bad_mouthing_q1_opt4"
                    ]
                ),
                DeepDiveQuestion(
                    questionKey: "deepdive_bad_mouthing_q2",
                    optionKeys: [
                        "deepdive_bad_mouthing_q2_opt1",
                        "deepdive_bad_mouthing_q2_opt2",
                        "deepdive_bad_mouthing_q2_opt3",
                        "deepdive_bad_mouthing_q2_opt4"
                    ]
                ),
                DeepDiveQuestion(
                    questionKey: "deepdive_bad_mouthing_q3",
                    optionKeys: [
                        "deepdive_bad_mouthing_q3_opt1",
                        "deepdive_bad_mouthing_q3_opt2",
                        "deepdive_bad_mouthing_q3_opt3",
                        "deepdive_bad_mouthing_q3_opt4"
                    ]
                )
            ]
        case .pornAddiction:
            return [
                DeepDiveQuestion(
                    questionKey: "deepdive_porn_addiction_q1",
                    optionKeys: [
                        "deepdive_porn_addiction_q1_opt1",
                        "deepdive_porn_addiction_q1_opt2",
                        "deepdive_porn_addiction_q1_opt3",
                        "deepdive_porn_addiction_q1_opt4"
                    ]
                ),
                DeepDiveQuestion(
                    questionKey: "deepdive_porn_addiction_q2",
                    optionKeys: [
                        "deepdive_porn_addiction_q2_opt1",
                        "deepdive_porn_addiction_q2_opt2",
                        "deepdive_porn_addiction_q2_opt3",
                        "deepdive_porn_addiction_q2_opt4"
                    ]
                )
            ]
        case .alcoholDependency:
            return [
                DeepDiveQuestion(
                    questionKey: "deepdive_alcohol_dependency_q1",
                    optionKeys: [
                        "deepdive_alcohol_dependency_q1_opt1",
                        "deepdive_alcohol_dependency_q1_opt2",
                        "deepdive_alcohol_dependency_q1_opt3",
                        "deepdive_alcohol_dependency_q1_opt4"
                    ]
                ),
                DeepDiveQuestion(
                    questionKey: "deepdive_alcohol_dependency_q2",
                    optionKeys: [
                        "deepdive_alcohol_dependency_q2_opt1",
                        "deepdive_alcohol_dependency_q2_opt2",
                        "deepdive_alcohol_dependency_q2_opt3",
                        "deepdive_alcohol_dependency_q2_opt4"
                    ]
                )
            ]
        case .anger:
            return [
                DeepDiveQuestion(
                    questionKey: "deepdive_anger_q1",
                    optionKeys: [
                        "deepdive_anger_q1_opt1",
                        "deepdive_anger_q1_opt2",
                        "deepdive_anger_q1_opt3",
                        "deepdive_anger_q1_opt4"
                    ]
                ),
                DeepDiveQuestion(
                    questionKey: "deepdive_anger_q2",
                    optionKeys: [
                        "deepdive_anger_q2_opt1",
                        "deepdive_anger_q2_opt2",
                        "deepdive_anger_q2_opt3",
                        "deepdive_anger_q2_opt4"
                    ]
                )
            ]
        case .obsessive:
            return [
                DeepDiveQuestion(
                    questionKey: "deepdive_obsessive_q1",
                    optionKeys: [
                        "deepdive_obsessive_q1_opt1",
                        "deepdive_obsessive_q1_opt2",
                        "deepdive_obsessive_q1_opt3",
                        "deepdive_obsessive_q1_opt4"
                    ]
                ),
                DeepDiveQuestion(
                    questionKey: "deepdive_obsessive_q2",
                    optionKeys: [
                        "deepdive_obsessive_q2_opt1",
                        "deepdive_obsessive_q2_opt2",
                        "deepdive_obsessive_q2_opt3",
                        "deepdive_obsessive_q2_opt4"
                    ]
                )
            ]
        case .loneliness:
            return [
                DeepDiveQuestion(
                    questionKey: "deepdive_loneliness_q1",
                    optionKeys: [
                        "deepdive_loneliness_q1_opt1",
                        "deepdive_loneliness_q1_opt2",
                        "deepdive_loneliness_q1_opt3",
                        "deepdive_loneliness_q1_opt4"
                    ]
                ),
                DeepDiveQuestion(
                    questionKey: "deepdive_loneliness_q2",
                    optionKeys: [
                        "deepdive_loneliness_q2_opt1",
                        "deepdive_loneliness_q2_opt2",
                        "deepdive_loneliness_q2_opt3",
                        "deepdive_loneliness_q2_opt4"
                    ]
                )
            ]
        }
    }
}
