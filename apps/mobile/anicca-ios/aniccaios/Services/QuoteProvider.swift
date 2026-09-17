import Foundation

/// Affirmation quote with stable id (for notification deep-link).
struct Quote: Identifiable, Codable, Hashable {
    let id: String
    let text: String
}

/// Medium-length single-sentence affirmations in the established autosuggestion tradition.
/// Themes: becoming, growth, presence, peace, love, confidence, gratitude, well-being.
/// Tone: spiritual / mindful — explicitly avoiding materialism (money flow / popularity / hedonism).
final class QuoteProvider {
    static let shared = QuoteProvider()
    private init() {}

    func all(preferredLanguage: LanguagePreference = LanguagePreference.detectDefault()) -> [Quote] {
        switch preferredLanguage {
        case .ja: return Self.ja
        case .es: return Self.es
        case .en, .de, .fr, .ptBR: return Self.en
        }
    }

    func byId(_ id: String, preferredLanguage: LanguagePreference = LanguagePreference.detectDefault()) -> Quote? {
        return all(preferredLanguage: preferredLanguage).first { $0.id == id }
    }

    func todayQuote(preferredLanguage: LanguagePreference, date: Date, calendar: Calendar = .current) -> String {
        let pool = all(preferredLanguage: preferredLanguage)
        let dayOfYear = calendar.ordinality(of: .day, in: .year, for: date) ?? 1
        let index = (dayOfYear - 1) % pool.count
        return pool[index].text
    }

    func todayQuote() -> String {
        return todayQuote(preferredLanguage: LanguagePreference.detectDefault(), date: Date())
    }

    // MARK: - Pools

    private static let en: [Quote] = [
        // Becoming / growth
        Quote(id: "q001", text: "I am committed to becoming who I am meant to be."),
        Quote(id: "q002", text: "I am constantly growing, learning, and unfolding."),
        Quote(id: "q003", text: "Every breath moves me closer to my truest self."),
        Quote(id: "q004", text: "I have a growth mindset, and I welcome every lesson."),
        Quote(id: "q005", text: "I trust the slow, beautiful work of my becoming."),
        Quote(id: "q006", text: "I let go of who I was, so I can meet who I am."),
        Quote(id: "q007", text: "I am exactly where I need to be in my journey."),
        Quote(id: "q008", text: "I am fully committed to living a meaningful life."),
        Quote(id: "q009", text: "I am open to the next version of myself."),
        Quote(id: "q010", text: "Each day, I move with quiet purpose."),

        // Love / connection
        Quote(id: "q011", text: "I am deeply, completely loved."),
        Quote(id: "q012", text: "I am surrounded by love in every direction."),
        Quote(id: "q013", text: "I am worthy of the love I give and receive."),
        Quote(id: "q014", text: "Love flows through me, easily and freely."),
        Quote(id: "q015", text: "I let love in. I let love out. Both are sacred."),
        Quote(id: "q016", text: "I am held by something greater than my fear."),
        Quote(id: "q017", text: "My heart is open to this moment, and to this life."),
        Quote(id: "q018", text: "I love myself enough to choose what is true."),
        Quote(id: "q019", text: "I see love in the smallest corners of my day."),
        Quote(id: "q020", text: "I am loved, and I let myself feel it."),

        // Peace / calm
        Quote(id: "q021", text: "I am at peace with where I am and where I am going."),
        Quote(id: "q022", text: "Peace lives within me. I return to it whenever I need."),
        Quote(id: "q023", text: "I am safe in this moment. I am safe in this breath."),
        Quote(id: "q024", text: "Stillness is my home. Quiet is my native language."),
        Quote(id: "q025", text: "I am calm at my center, even when the world is loud."),
        Quote(id: "q026", text: "I rest in the quiet space between my thoughts."),
        Quote(id: "q027", text: "I do not need to fix everything. I am allowed to rest."),
        Quote(id: "q028", text: "I breathe in calm. I breathe out tension."),
        Quote(id: "q029", text: "I am gentle with myself, especially on hard days."),
        Quote(id: "q030", text: "I am soft enough to bend, strong enough to stay."),

        // Presence / now
        Quote(id: "q031", text: "I am here, now. That is enough."),
        Quote(id: "q032", text: "This breath is enough. This moment is enough."),
        Quote(id: "q033", text: "I am awake to the small wonders of my day."),
        Quote(id: "q034", text: "I do not need to chase. The moment finds me."),
        Quote(id: "q035", text: "I let this moment be exactly as it is."),
        Quote(id: "q036", text: "I return to my breath. I return to myself."),
        Quote(id: "q037", text: "I am present in this body, this place, this hour."),
        Quote(id: "q038", text: "I notice. I breathe. I begin again."),
        Quote(id: "q039", text: "Everything I need is in this moment."),
        Quote(id: "q040", text: "I belong to this breath, and this breath belongs to me."),

        // Self-confidence / inner strength
        Quote(id: "q041", text: "I have everything within me to live this life."),
        Quote(id: "q042", text: "I trust my voice, my path, and my own timing."),
        Quote(id: "q043", text: "I am the steady ground beneath my own feet."),
        Quote(id: "q044", text: "I am whole, exactly as I am, in this very hour."),
        Quote(id: "q045", text: "I am my own best chance for a meaningful life."),
        Quote(id: "q046", text: "I am stronger than the thoughts that try to shrink me."),
        Quote(id: "q047", text: "I trust myself to walk through whatever comes."),
        Quote(id: "q048", text: "I have the strength to live with a growth mindset."),
        Quote(id: "q049", text: "I am allowed to take up space in this life."),
        Quote(id: "q050", text: "I am steady. I am steady. I am steady."),

        // Gratitude / well-being / abundance (non-material)
        Quote(id: "q051", text: "I am grateful for the breath I take, right this second."),
        Quote(id: "q052", text: "I am grateful for the body that carries me through today."),
        Quote(id: "q053", text: "Today, I notice what is good, and I let it grow."),
        Quote(id: "q054", text: "I am happy, healthy, and centered in myself."),
        Quote(id: "q055", text: "I have everything I need, exactly when I need it."),
        Quote(id: "q056", text: "I am open to receive what life offers me today."),
        Quote(id: "q057", text: "I trust that the right things come in the right time."),
        Quote(id: "q058", text: "I know abundance lives inside me, not outside."),
        Quote(id: "q059", text: "I am rich in the things that cannot be counted."),
        Quote(id: "q060", text: "I am thankful for everything that is, and everything I am."),

        // Resilience / weathering hardship
        Quote(id: "q061", text: "I have weathered hard days before, and I will weather this one too."),
        Quote(id: "q062", text: "I bend with the storm, and I do not break."),
        Quote(id: "q063", text: "Difficulty passes through me; it does not define me."),
        Quote(id: "q064", text: "I am still standing, and that is its own quiet victory."),
        Quote(id: "q065", text: "Every hardship has taught me something I needed to know."),
        Quote(id: "q066", text: "I meet this challenge with steady, open hands."),
        Quote(id: "q067", text: "I am more resilient than my hardest moment."),
        Quote(id: "q068", text: "What is heavy today will be lighter tomorrow."),
        Quote(id: "q069", text: "I let difficulty soften me, not harden me."),
        Quote(id: "q070", text: "I rise, gently and surely, as many times as I need to."),

        // Letting go / acceptance
        Quote(id: "q071", text: "I release what I cannot control, and I keep my peace."),
        Quote(id: "q072", text: "I let go of the need to have it all figured out."),
        Quote(id: "q073", text: "I loosen my grip, and I feel myself breathe again."),
        Quote(id: "q074", text: "What is meant to leave, I let leave."),
        Quote(id: "q075", text: "I set down the weight I was never meant to carry."),
        Quote(id: "q076", text: "I make peace with endings, and with what comes after."),
        Quote(id: "q077", text: "I release old stories that no longer serve me."),
        Quote(id: "q078", text: "I allow life to be uncertain, and I stay soft inside it."),
        Quote(id: "q079", text: "I let the river carry what is no longer mine."),
        Quote(id: "q080", text: "I open my hands, and I let the moment be free."),

        // Body / breath / vitality
        Quote(id: "q081", text: "My body is a good and faithful home."),
        Quote(id: "q082", text: "I breathe deeply, and my whole body softens."),
        Quote(id: "q083", text: "I thank my body for all it quietly does for me."),
        Quote(id: "q084", text: "Energy moves through me, clear and unhurried."),
        Quote(id: "q085", text: "I rest when I am tired, and I trust that rest is enough."),
        Quote(id: "q086", text: "I treat my body with the care I would give a friend."),
        Quote(id: "q087", text: "Each breath fills me with quiet, steady life."),
        Quote(id: "q088", text: "I am at home in my own skin."),
        Quote(id: "q089", text: "I move through my day with ease and gentleness."),
        Quote(id: "q090", text: "My body and my mind are on the same calm side."),

        // Self-compassion / forgiveness
        Quote(id: "q091", text: "I forgive myself for not knowing what I had not yet learned."),
        Quote(id: "q092", text: "I speak to myself the way I would speak to someone I love."),
        Quote(id: "q093", text: "I am allowed to be a work in progress."),
        Quote(id: "q094", text: "I release the harsh judge inside me, and I choose kindness."),
        Quote(id: "q095", text: "My mistakes are part of my becoming, not proof against me."),
        Quote(id: "q096", text: "I let my old regrets rest, and I begin from here."),
        Quote(id: "q097", text: "I am gentle with the parts of me that are still healing."),
        Quote(id: "q098", text: "I deserve the same compassion I so freely give others."),
        Quote(id: "q099", text: "I forgive, so I can carry less and walk farther."),
        Quote(id: "q100", text: "I meet my own imperfection with a soft and open heart."),

        // Courage / meeting fear
        Quote(id: "q101", text: "I can feel afraid and still move forward."),
        Quote(id: "q102", text: "Courage is not the absence of fear; it is my answer to it."),
        Quote(id: "q103", text: "I do the brave thing, one small step at a time."),
        Quote(id: "q104", text: "I trust myself to handle what I am afraid of."),
        Quote(id: "q105", text: "Fear is a visitor; I do not let it run my house."),
        Quote(id: "q106", text: "I walk toward what matters, even when my heart pounds."),
        Quote(id: "q107", text: "I am braver than I was yesterday."),
        Quote(id: "q108", text: "I let my courage be quiet, and still it carries me."),
        Quote(id: "q109", text: "I face this moment with an open and steady heart."),
        Quote(id: "q110", text: "I choose growth over the comfort of staying small."),

        // Trust / surrender
        Quote(id: "q111", text: "I trust that life is unfolding as it needs to."),
        Quote(id: "q112", text: "I surrender my grip and let life meet me halfway."),
        Quote(id: "q113", text: "I trust the ground to hold me, even when I cannot see it."),
        Quote(id: "q114", text: "I do not have to know the whole path to take the next step."),
        Quote(id: "q115", text: "I trust that what I need will find me in time."),
        Quote(id: "q116", text: "I let go, and I am still held."),
        Quote(id: "q117", text: "I trust the quiet wisdom that lives within me."),
        Quote(id: "q118", text: "I lean into life, and life leans back."),
        Quote(id: "q119", text: "I release my plans gently and stay open to better ones."),
        Quote(id: "q120", text: "I am carried by something larger than my worry."),

        // Purpose / contribution
        Quote(id: "q121", text: "My life has meaning, simply because I am living it well."),
        Quote(id: "q122", text: "I offer my small kindness to the world today."),
        Quote(id: "q123", text: "I am here to grow, to love, and to leave things gentler."),
        Quote(id: "q124", text: "My presence is a quiet gift to those around me."),
        Quote(id: "q125", text: "I serve life best by becoming fully myself."),
        Quote(id: "q126", text: "I do my work with care, and I let that be enough."),
        Quote(id: "q127", text: "I leave each place a little kinder than I found it."),
        Quote(id: "q128", text: "My purpose reveals itself one honest day at a time."),
        Quote(id: "q129", text: "I matter, and what I do with my hours matters."),
        Quote(id: "q130", text: "I give what I can, and I trust that it is enough."),

        // Joy / lightness
        Quote(id: "q131", text: "I let myself enjoy this ordinary, beautiful day."),
        Quote(id: "q132", text: "Joy is allowed to find me, even now."),
        Quote(id: "q133", text: "I make room for laughter and for lightness."),
        Quote(id: "q134", text: "I notice one small delight, and I let it bloom."),
        Quote(id: "q135", text: "I do not have to earn my own happiness."),
        Quote(id: "q136", text: "I let wonder soften the edges of my day."),
        Quote(id: "q137", text: "I am allowed to feel good, simply because I am alive."),
        Quote(id: "q138", text: "I welcome joy without waiting for permission."),
        Quote(id: "q139", text: "I take my play as seriously as my work."),
        Quote(id: "q140", text: "I let a quiet smile find its way back to me."),

        // Clarity / quiet mind
        Quote(id: "q141", text: "My mind grows quiet, and clarity rises on its own."),
        Quote(id: "q142", text: "I let my thoughts settle like dust in still water."),
        Quote(id: "q143", text: "I do not believe every thought that passes through me."),
        Quote(id: "q144", text: "I return, again and again, to what truly matters."),
        Quote(id: "q145", text: "I make space between my thoughts, and I breathe there."),
        Quote(id: "q146", text: "My mind is clear, and my next step is simple."),
        Quote(id: "q147", text: "I let go of the noise and listen for the quiet truth."),
        Quote(id: "q148", text: "I focus on this one thing, gently and fully."),
        Quote(id: "q149", text: "A calm mind is a clear mind, and I am calm."),
        Quote(id: "q150", text: "I trust the answers that arrive in stillness."),

        // Patience / timing
        Quote(id: "q151", text: "I trust the slow, patient unfolding of my life."),
        Quote(id: "q152", text: "Good things grow in their own quiet time."),
        Quote(id: "q153", text: "I am patient with myself, and with the road ahead."),
        Quote(id: "q154", text: "I do not rush what is meant to ripen slowly."),
        Quote(id: "q155", text: "I let today be a small, faithful step."),
        Quote(id: "q156", text: "I trust that I am not behind; I am right on time."),
        Quote(id: "q157", text: "Patience is a kind of love I give myself."),
        Quote(id: "q158", text: "I plant seeds today and trust the season to come."),
        Quote(id: "q159", text: "I move at the pace of peace, not the pace of fear."),
        Quote(id: "q160", text: "I let life take the time it needs to bloom."),

        // Worthiness / enough
        Quote(id: "q161", text: "I am enough, exactly as I am, right now."),
        Quote(id: "q162", text: "I have nothing to prove and nothing to earn."),
        Quote(id: "q163", text: "My worth is not measured by what I produce."),
        Quote(id: "q164", text: "I am worthy of rest, of joy, and of good things."),
        Quote(id: "q165", text: "I belong here, simply because I am here."),
        Quote(id: "q166", text: "I do not need to be perfect to be worthy."),
        Quote(id: "q167", text: "I am whole, even on the days I feel unfinished."),
        Quote(id: "q168", text: "I accept myself fully, without conditions."),
        Quote(id: "q169", text: "I am worthy of my own time and my own care."),
        Quote(id: "q170", text: "I am already enough, and I am still growing."),

        // Belonging / kindness to others
        Quote(id: "q171", text: "I am connected to every living thing around me."),
        Quote(id: "q172", text: "I offer kindness, and it returns to me in quiet ways."),
        Quote(id: "q173", text: "I am not alone; I am part of something larger."),
        Quote(id: "q174", text: "I let others in, and I let myself be seen."),
        Quote(id: "q175", text: "I meet the people in my day with an open heart."),
        Quote(id: "q176", text: "I belong, simply and fully, to this shared life."),
        Quote(id: "q177", text: "I give patience to others, as I would want for myself."),
        Quote(id: "q178", text: "I am held by a web of unseen kindness."),
        Quote(id: "q179", text: "I see the quiet struggle in others, and I am gentle."),
        Quote(id: "q180", text: "I am a small, warm light in someone's day."),

        // Healing / renewal / fresh starts
        Quote(id: "q181", text: "I am healing, a little more, with every passing day."),
        Quote(id: "q182", text: "Each morning offers me a clean and open page."),
        Quote(id: "q183", text: "I let what hurt me become what teaches me."),
        Quote(id: "q184", text: "I am allowed to begin again, as often as I need."),
        Quote(id: "q185", text: "I release yesterday and welcome this new light."),
        Quote(id: "q186", text: "I am gentle with my healing; it has its own pace."),
        Quote(id: "q187", text: "I make peace with my past and turn toward the morning."),
        Quote(id: "q188", text: "I am renewed by rest, by breath, and by time."),
        Quote(id: "q189", text: "Old wounds soften as I hold them with care."),
        Quote(id: "q190", text: "I rise into this day as someone slightly more whole."),

        // Equanimity / impermanence (anicca)
        Quote(id: "q191", text: "Everything changes, and I move gently with the change."),
        Quote(id: "q192", text: "This too will pass, and I will still be here, breathing."),
        Quote(id: "q193", text: "I hold both joy and sorrow with the same open hand."),
        Quote(id: "q194", text: "Nothing stays; so I love this moment while it is here."),
        Quote(id: "q195", text: "I let feelings rise and fall like waves, and I remain."),
        Quote(id: "q196", text: "I am the still water beneath the passing weather."),
        Quote(id: "q197", text: "I accept the rhythm of arriving and letting go."),
        Quote(id: "q198", text: "Impermanence is not loss; it is life, moving."),
        Quote(id: "q199", text: "I rest in the calm that does not depend on conditions."),
        Quote(id: "q200", text: "All things flow, and I flow peacefully with them."),
    ]

    private static let ja: [Quote] = [
        // 本当の自分になる
        Quote(id: "q001", text: "私は本当の自分になりつつあります。"),
        Quote(id: "q002", text: "私は日々、学び、成長し、開かれていきます。"),
        Quote(id: "q003", text: "一呼吸ごとに、本当の自分に近づいています。"),
        Quote(id: "q004", text: "私はあらゆる経験から、静かに学んでいます。"),
        Quote(id: "q005", text: "私は、自分が育つ速さを信頼しています。"),
        Quote(id: "q006", text: "過去の自分を手放し、今の自分を迎えます。"),
        Quote(id: "q007", text: "私は今、ちょうど良い場所にいます。"),
        Quote(id: "q008", text: "私は意味のある人生を、心から生きています。"),
        Quote(id: "q009", text: "私はこれから現れる自分を、楽しみにしています。"),
        Quote(id: "q010", text: "私は毎日、静かな目的を持って歩いています。"),

        // 愛・つながり
        Quote(id: "q011", text: "私は深く、まるごと愛されています。"),
        Quote(id: "q012", text: "私はあらゆる方向から、愛に包まれています。"),
        Quote(id: "q013", text: "私は、愛を受け取り、愛を与える存在です。"),
        Quote(id: "q014", text: "愛は私を通って、軽やかに流れています。"),
        Quote(id: "q015", text: "私はいつでも、愛を感じることができます。"),
        Quote(id: "q016", text: "私は恐れより、大きなものに抱かれています。"),
        Quote(id: "q017", text: "私の心は、この瞬間と人生に開かれています。"),
        Quote(id: "q018", text: "私は、真実を選べるくらい自分を愛しています。"),
        Quote(id: "q019", text: "私は、日常の小さな愛に気づいています。"),
        Quote(id: "q020", text: "私は愛されている、と感じることを自分に許します。"),

        // 平和・静けさ
        Quote(id: "q021", text: "私は、今いる場所にも、向かう先にも平和を感じます。"),
        Quote(id: "q022", text: "私の中心には、いつでも戻れる静けさがあります。"),
        Quote(id: "q023", text: "この瞬間、この呼吸の中で、私は安全です。"),
        Quote(id: "q024", text: "静けさは私の故郷であり、私の母国語です。"),
        Quote(id: "q025", text: "外がどれほど騒がしくても、私の中心は穏やかです。"),
        Quote(id: "q026", text: "私は思考の合間にある、静かな空間に休みます。"),
        Quote(id: "q027", text: "すべてを直さなくていい。私は休んでよいのです。"),
        Quote(id: "q028", text: "穏やかさを吸い、緊張を吐き出します。"),
        Quote(id: "q029", text: "私は、特に辛い日こそ、自分に優しくします。"),
        Quote(id: "q030", text: "私は、しなやかで、そして揺るぎない存在です。"),

        // 今ここ・存在
        Quote(id: "q031", text: "私は今、ここに在ります。それで十分です。"),
        Quote(id: "q032", text: "この呼吸で十分。この瞬間で十分です。"),
        Quote(id: "q033", text: "私は、今日の小さな美しさに気づいています。"),
        Quote(id: "q034", text: "追いかける必要はありません。今が私を見つけます。"),
        Quote(id: "q035", text: "私は、この瞬間をあるがままに受け入れます。"),
        Quote(id: "q036", text: "私は呼吸に戻り、自分自身に戻ります。"),
        Quote(id: "q037", text: "私は、この体、この場所、この時間に在ります。"),
        Quote(id: "q038", text: "気づき、息をして、もう一度始めます。"),
        Quote(id: "q039", text: "私に必要なものは、すべて今この瞬間にあります。"),
        Quote(id: "q040", text: "私はこの呼吸に属し、この呼吸は私のものです。"),

        // 自信・内なる力
        Quote(id: "q041", text: "私はこの人生を生きる力を、すべて持っています。"),
        Quote(id: "q042", text: "私は自分の声、自分の道、自分の時間を信頼しています。"),
        Quote(id: "q043", text: "私は、自分の足元にある確かな大地です。"),
        Quote(id: "q044", text: "私は今のままで、ちょうど完全です。"),
        Quote(id: "q045", text: "私は、意味のある人生を生きる最大の味方です。"),
        Quote(id: "q046", text: "私は、自分を小さくしようとする声より強い。"),
        Quote(id: "q047", text: "何が来ても、自分で歩いていけると信じています。"),
        Quote(id: "q048", text: "私は、成長する心で生きる力を持っています。"),
        Quote(id: "q049", text: "私は、この人生の中で居場所を持っていいのです。"),
        Quote(id: "q050", text: "私は揺るぎなく、揺るぎなく、揺るぎなくここにいます。"),

        // 感謝・健やかさ・豊かさ
        Quote(id: "q051", text: "私は今、この一呼吸に深く感謝しています。"),
        Quote(id: "q052", text: "私は、今日も私を運んでくれる体に感謝しています。"),
        Quote(id: "q053", text: "今日も、良いことに気づき、それを静かに育てます。"),
        Quote(id: "q054", text: "私は幸せで、健康で、自分の中心にいます。"),
        Quote(id: "q055", text: "私は必要なものを、ちょうど良い時に受け取ります。"),
        Quote(id: "q056", text: "私は、今日が差し出すものに、心を開いています。"),
        Quote(id: "q057", text: "ふさわしいものが、ふさわしい時に訪れると信じます。"),
        Quote(id: "q058", text: "豊かさは外ではなく、私の内側にあると知っています。"),
        Quote(id: "q059", text: "私は、数えられないものを、たくさん持っています。"),
        Quote(id: "q060", text: "私は、ある全てと、ある自分に、深く感謝しています。"),

        // レジリエンス・困難
        Quote(id: "q061", text: "私は今までも辛い日を越えてきた。今日も越えていけます。"),
        Quote(id: "q062", text: "私は嵐にしなり、そして折れません。"),
        Quote(id: "q063", text: "困難は私を通り過ぎていく。私を決めるものではありません。"),
        Quote(id: "q064", text: "私はまだ立っている。それだけで静かな勝利です。"),
        Quote(id: "q065", text: "どんな苦しみも、私に必要な何かを教えてくれました。"),
        Quote(id: "q066", text: "私はこの試練を、落ち着いた開いた手で迎えます。"),
        Quote(id: "q067", text: "私は、いちばん辛かった瞬間よりも強い。"),
        Quote(id: "q068", text: "今日重いものは、明日にはきっと軽くなります。"),
        Quote(id: "q069", text: "私は困難に、硬くなるのではなく、優しくなります。"),
        Quote(id: "q070", text: "私は必要なだけ、何度でも静かに立ち上がります。"),

        // 手放す・受け入れる
        Quote(id: "q071", text: "コントロールできないことを手放し、平和を保ちます。"),
        Quote(id: "q072", text: "すべてを分かっていなくていい、と自分を許します。"),
        Quote(id: "q073", text: "握りしめた手をゆるめると、また呼吸ができます。"),
        Quote(id: "q074", text: "去るべきものは、去るにまかせます。"),
        Quote(id: "q075", text: "背負わなくていい重さを、私はそっと下ろします。"),
        Quote(id: "q076", text: "私は終わりと、その後に来るものと、和解します。"),
        Quote(id: "q077", text: "もう役に立たない古い物語を、私は手放します。"),
        Quote(id: "q078", text: "人生が不確かでも、その中で私は穏やかでいられます。"),
        Quote(id: "q079", text: "もう私のものでないものは、川に流れるにまかせます。"),
        Quote(id: "q080", text: "私は手を開き、この瞬間を自由にします。"),

        // 体・呼吸・活力
        Quote(id: "q081", text: "私の体は、良き、誠実な住まいです。"),
        Quote(id: "q082", text: "深く息を吸うと、体ぜんぶがゆるみます。"),
        Quote(id: "q083", text: "私は、静かに働いてくれる体に感謝します。"),
        Quote(id: "q084", text: "エネルギーが、澄んで、急がず、私を巡ります。"),
        Quote(id: "q085", text: "疲れたら休む。その休みで十分だと信じます。"),
        Quote(id: "q086", text: "私は、友にするように自分の体をいたわります。"),
        Quote(id: "q087", text: "一呼吸ごとに、静かで確かな命が満ちていきます。"),
        Quote(id: "q088", text: "私は、自分の体の中でくつろいでいます。"),
        Quote(id: "q089", text: "私は、軽やかさと優しさで一日を歩きます。"),
        Quote(id: "q090", text: "私の体と心は、同じ穏やかな側にいます。"),

        // 自分への思いやり・許し
        Quote(id: "q091", text: "まだ知らなかったことを、知らなかった自分を許します。"),
        Quote(id: "q092", text: "大切な人に話すように、自分に語りかけます。"),
        Quote(id: "q093", text: "私は、まだ途中の自分でいていいのです。"),
        Quote(id: "q094", text: "私の中の厳しい裁き手を手放し、優しさを選びます。"),
        Quote(id: "q095", text: "失敗は私の成長の一部で、私を責める証拠ではありません。"),
        Quote(id: "q096", text: "古い後悔を休ませ、私はここから始めます。"),
        Quote(id: "q097", text: "まだ癒えていない部分に、私は優しくします。"),
        Quote(id: "q098", text: "人に与える思いやりを、私は自分にも向けます。"),
        Quote(id: "q099", text: "私は許す。だから軽くなり、遠くまで歩けます。"),
        Quote(id: "q100", text: "私は、自分の不完全さを、柔らかな心で迎えます。"),

        // 勇気・恐れに向き合う
        Quote(id: "q101", text: "怖くても、私は前に進むことができます。"),
        Quote(id: "q102", text: "勇気とは恐れがないことではなく、恐れへの私の答えです。"),
        Quote(id: "q103", text: "私は勇気ある一歩を、小さく、少しずつ踏み出します。"),
        Quote(id: "q104", text: "怖いものに向き合える、と自分を信じます。"),
        Quote(id: "q105", text: "恐れは訪問者。私は家の主導権を渡しません。"),
        Quote(id: "q106", text: "胸が高鳴っても、私は大切なものへ歩きます。"),
        Quote(id: "q107", text: "私は昨日より、少し勇敢です。"),
        Quote(id: "q108", text: "私の勇気は静かでも、ちゃんと私を運びます。"),
        Quote(id: "q109", text: "私は、開いた落ち着いた心でこの瞬間に向き合います。"),
        Quote(id: "q110", text: "小さくとどまる安心より、成長を選びます。"),

        // 信頼・委ねる
        Quote(id: "q111", text: "人生は必要なように展開している、と信じます。"),
        Quote(id: "q112", text: "握る手をゆるめ、人生が半分まで来るのにまかせます。"),
        Quote(id: "q113", text: "見えなくても、大地は私を支えていると信じます。"),
        Quote(id: "q114", text: "道の全体が見えなくても、次の一歩は踏み出せます。"),
        Quote(id: "q115", text: "必要なものは、時が来れば私を見つけると信じます。"),
        Quote(id: "q116", text: "私は手放す。それでも私は支えられています。"),
        Quote(id: "q117", text: "私は、内に宿る静かな知恵を信頼します。"),
        Quote(id: "q118", text: "私が人生に寄りかかると、人生も寄りかかってくれます。"),
        Quote(id: "q119", text: "計画をそっと手放し、より良いものに開いておきます。"),
        Quote(id: "q120", text: "私は、心配より大きな何かに運ばれています。"),

        // 目的・貢献
        Quote(id: "q121", text: "私の人生は、よく生きるだけで意味があります。"),
        Quote(id: "q122", text: "今日、私は世界に小さな優しさを差し出します。"),
        Quote(id: "q123", text: "私は、育ち、愛し、物事をやわらげるためにここにいます。"),
        Quote(id: "q124", text: "私の存在は、まわりへの静かな贈り物です。"),
        Quote(id: "q125", text: "私は、自分自身に成りきることで、命に仕えます。"),
        Quote(id: "q126", text: "私は丁寧に務めを果たし、それで十分とします。"),
        Quote(id: "q127", text: "私は、出会った場所を少しだけ優しくして去ります。"),
        Quote(id: "q128", text: "私の目的は、誠実な一日ごとに姿を現します。"),
        Quote(id: "q129", text: "私は大切な存在で、時間の使い方も大切です。"),
        Quote(id: "q130", text: "できることを差し出し、それで十分だと信じます。"),

        // 喜び・軽やかさ
        Quote(id: "q131", text: "私は、この平凡で美しい一日を楽しみます。"),
        Quote(id: "q132", text: "喜びは今この瞬間も、私を見つけていいのです。"),
        Quote(id: "q133", text: "私は、笑いと軽やかさのための余白をつくります。"),
        Quote(id: "q134", text: "小さな喜びにひとつ気づき、それを咲かせます。"),
        Quote(id: "q135", text: "私は、自分の幸せを稼ぐ必要はありません。"),
        Quote(id: "q136", text: "私は、驚きで一日の角をやわらげます。"),
        Quote(id: "q137", text: "私は、生きているというだけで、心地よくていいのです。"),
        Quote(id: "q138", text: "許可を待たずに、私は喜びを迎え入れます。"),
        Quote(id: "q139", text: "私は、遊びを仕事と同じくらい大切にします。"),
        Quote(id: "q140", text: "静かな微笑みが、私のもとに戻ってきます。"),

        // 明晰・静かな心
        Quote(id: "q141", text: "心が静まると、明晰さがひとりでに立ちのぼります。"),
        Quote(id: "q142", text: "私は、思考が澄んだ水の塵のように沈むにまかせます。"),
        Quote(id: "q143", text: "通り過ぎるすべての思考を、私は信じ込みません。"),
        Quote(id: "q144", text: "私は何度でも、本当に大切なものへ戻ります。"),
        Quote(id: "q145", text: "思考の間に空間をつくり、そこで呼吸します。"),
        Quote(id: "q146", text: "心は澄み、次の一歩はシンプルです。"),
        Quote(id: "q147", text: "雑音を手放し、静かな真実に耳をすませます。"),
        Quote(id: "q148", text: "私は、この一つのことに、やさしく深く集中します。"),
        Quote(id: "q149", text: "穏やかな心は澄んだ心。そして私は穏やかです。"),
        Quote(id: "q150", text: "静けさの中に訪れる答えを、私は信頼します。"),

        // 忍耐・時
        Quote(id: "q151", text: "私は、人生のゆっくりとした展開を信頼します。"),
        Quote(id: "q152", text: "良いものは、それぞれの静かな時に育ちます。"),
        Quote(id: "q153", text: "私は、自分にも、これからの道にも忍耐強くいます。"),
        Quote(id: "q154", text: "ゆっくり熟すべきものを、私は急がせません。"),
        Quote(id: "q155", text: "今日が、小さな誠実な一歩であればいい。"),
        Quote(id: "q156", text: "私は遅れていない。ちょうど良い時にいます。"),
        Quote(id: "q157", text: "忍耐は、私が自分に贈る愛のかたちです。"),
        Quote(id: "q158", text: "今日種をまき、巡る季節を信じます。"),
        Quote(id: "q159", text: "恐れの速さではなく、平和の速さで進みます。"),
        Quote(id: "q160", text: "人生が咲くのに必要な時間を、私は与えます。"),

        // 価値・十分であること
        Quote(id: "q161", text: "私は今このままで、十分です。"),
        Quote(id: "q162", text: "私には、証明することも、稼ぐこともありません。"),
        Quote(id: "q163", text: "私の価値は、生み出した量では測れません。"),
        Quote(id: "q164", text: "私は、休みも、喜びも、良きものも受け取る価値があります。"),
        Quote(id: "q165", text: "私はここにいる、ただそれだけで、ここに属します。"),
        Quote(id: "q166", text: "完璧でなくても、私には価値があります。"),
        Quote(id: "q167", text: "未完成に感じる日も、私は欠けていません。"),
        Quote(id: "q168", text: "私は、条件をつけずに自分を受け入れます。"),
        Quote(id: "q169", text: "私は、自分の時間と手当てに値する存在です。"),
        Quote(id: "q170", text: "私はすでに十分で、そしてまだ育っています。"),

        // つながり・他者への優しさ
        Quote(id: "q171", text: "私は、まわりのすべての命とつながっています。"),
        Quote(id: "q172", text: "差し出した優しさは、静かな形で私に戻ります。"),
        Quote(id: "q173", text: "私は独りではない。大きな何かの一部です。"),
        Quote(id: "q174", text: "私は人を招き入れ、自分を見せることを許します。"),
        Quote(id: "q175", text: "私は、今日出会う人を、開いた心で迎えます。"),
        Quote(id: "q176", text: "私は、この分かち合う命に、まるごと属します。"),
        Quote(id: "q177", text: "自分が望むように、他者にも忍耐を差し出します。"),
        Quote(id: "q178", text: "私は、目に見えない優しさの網に支えられています。"),
        Quote(id: "q179", text: "他者の静かな苦しみに気づき、私は優しくします。"),
        Quote(id: "q180", text: "私は、誰かの一日を照らす小さな温かい光です。"),

        // 癒し・再生・新しい始まり
        Quote(id: "q181", text: "私は、日が経つごとに少しずつ癒えています。"),
        Quote(id: "q182", text: "毎朝が、まっさらな開かれたページを差し出します。"),
        Quote(id: "q183", text: "私を傷つけたものを、私を教えるものに変えます。"),
        Quote(id: "q184", text: "私は必要なだけ、何度でも始め直していいのです。"),
        Quote(id: "q185", text: "昨日を手放し、この新しい光を迎えます。"),
        Quote(id: "q186", text: "私は自分の癒しに優しくする。それには独自の速さがあります。"),
        Quote(id: "q187", text: "過去と和解し、私は朝のほうへ向きます。"),
        Quote(id: "q188", text: "私は、休みと、呼吸と、時間によって生まれ変わります。"),
        Quote(id: "q189", text: "古い傷は、丁寧に抱くほどにやわらいでいきます。"),
        Quote(id: "q190", text: "私は、少しだけ満たされた自分として、この日に立ち上がります。"),

        // 平静・無常（アニッチャ）
        Quote(id: "q191", text: "すべては移ろう。私はその移ろいと、そっと共に進みます。"),
        Quote(id: "q192", text: "これもまた過ぎ去る。それでも私はここで息をしています。"),
        Quote(id: "q193", text: "喜びも悲しみも、私は同じ開いた手で抱きます。"),
        Quote(id: "q194", text: "何も留まらない。だから今この瞬間を愛します。"),
        Quote(id: "q195", text: "感情は波のように上がっては引く。私はとどまります。"),
        Quote(id: "q196", text: "私は、移りゆく天気の下の、静かな水です。"),
        Quote(id: "q197", text: "私は、訪れることと、手放すことのリズムを受け入れます。"),
        Quote(id: "q198", text: "無常は喪失ではなく、動いている命そのものです。"),
        Quote(id: "q199", text: "条件に左右されない静けさの中に、私は憩います。"),
        Quote(id: "q200", text: "すべては流れる。私も穏やかに、ともに流れます。"),
    ]

    private static let es: [Quote] = [
        // Becoming / convertirse
        Quote(id: "q001", text: "Me estoy convirtiendo en quien estoy destinado a ser."),
        Quote(id: "q002", text: "Crezco, aprendo y me abro un poco más cada día."),
        Quote(id: "q003", text: "Cada respiración me acerca a mi yo verdadero."),
        Quote(id: "q004", text: "Aprendo en silencio de cada experiencia."),
        Quote(id: "q005", text: "Confío en el ritmo de mi propio crecimiento."),
        Quote(id: "q006", text: "Suelto quien fui para recibir quien soy."),
        Quote(id: "q007", text: "Estoy exactamente donde necesito estar."),
        Quote(id: "q008", text: "Vivo una vida con sentido, sin prisa."),
        Quote(id: "q009", text: "Me abro a la próxima versión de mí mismo."),
        Quote(id: "q010", text: "Cada día camino con un propósito tranquilo."),

        // Love / amor
        Quote(id: "q011", text: "Soy profundamente amado."),
        Quote(id: "q012", text: "Estoy rodeado de amor en todas direcciones."),
        Quote(id: "q013", text: "Merezco el amor que doy y el que recibo."),
        Quote(id: "q014", text: "El amor fluye a través de mí con suavidad."),
        Quote(id: "q015", text: "Siempre puedo sentir el amor que me rodea."),
        Quote(id: "q016", text: "Algo más grande que mi miedo me sostiene."),
        Quote(id: "q017", text: "Mi corazón está abierto a este momento y a esta vida."),
        Quote(id: "q018", text: "Me amo lo suficiente para elegir lo verdadero."),
        Quote(id: "q019", text: "Veo amor en los pequeños rincones de mi día."),
        Quote(id: "q020", text: "Soy amado, y me permito sentirlo."),

        // Peace / paz
        Quote(id: "q021", text: "Estoy en paz con donde estoy y hacia dónde voy."),
        Quote(id: "q022", text: "Llevo dentro un silencio al que siempre puedo volver."),
        Quote(id: "q023", text: "En este instante, en esta respiración, estoy a salvo."),
        Quote(id: "q024", text: "El silencio es mi hogar."),
        Quote(id: "q025", text: "Mi centro permanece tranquilo aunque el mundo grite."),
        Quote(id: "q026", text: "Descanso en el espacio entre mis pensamientos."),
        Quote(id: "q027", text: "No tengo que arreglarlo todo. Puedo descansar."),
        Quote(id: "q028", text: "Inhalo calma. Exhalo tensión."),
        Quote(id: "q029", text: "Soy amable conmigo, especialmente los días difíciles."),
        Quote(id: "q030", text: "Soy lo bastante suave para doblarme, lo bastante fuerte para quedarme."),

        // Presence / presencia
        Quote(id: "q031", text: "Aquí estoy, ahora. Es suficiente."),
        Quote(id: "q032", text: "Esta respiración basta. Este momento basta."),
        Quote(id: "q033", text: "Estoy despierto a las pequeñas maravillas del día."),
        Quote(id: "q034", text: "No tengo que perseguir. El momento me encuentra."),
        Quote(id: "q035", text: "Permito que este instante sea exactamente como es."),
        Quote(id: "q036", text: "Vuelvo a mi respiración. Vuelvo a mí."),
        Quote(id: "q037", text: "Estoy presente en este cuerpo, este lugar, esta hora."),
        Quote(id: "q038", text: "Observo. Respiro. Comienzo de nuevo."),
        Quote(id: "q039", text: "Todo lo que necesito vive en este momento."),
        Quote(id: "q040", text: "Pertenezco a esta respiración, y ella me pertenece."),

        // Confidence / confianza
        Quote(id: "q041", text: "Tengo dentro de mí todo lo necesario para vivir esta vida."),
        Quote(id: "q042", text: "Confío en mi voz, mi camino y mi propio tiempo."),
        Quote(id: "q043", text: "Soy la tierra firme bajo mis propios pies."),
        Quote(id: "q044", text: "Soy completo, tal como soy, en esta hora."),
        Quote(id: "q045", text: "Soy mi mejor oportunidad para una vida con sentido."),
        Quote(id: "q046", text: "Soy más fuerte que la voz que intenta empequeñecerme."),
        Quote(id: "q047", text: "Confío en mí para atravesar lo que venga."),
        Quote(id: "q048", text: "Tengo la fuerza para vivir con mente abierta."),
        Quote(id: "q049", text: "Tengo permiso para ocupar mi espacio en esta vida."),
        Quote(id: "q050", text: "Estoy firme. Estoy firme. Estoy firme."),

        // Gratitude / gratitud
        Quote(id: "q051", text: "Agradezco esta respiración, justo ahora."),
        Quote(id: "q052", text: "Agradezco a este cuerpo que me lleva por hoy."),
        Quote(id: "q053", text: "Hoy noto lo bueno y lo dejo crecer."),
        Quote(id: "q054", text: "Soy feliz, sano y centrado en mí mismo."),
        Quote(id: "q055", text: "Recibo lo que necesito, justo cuando lo necesito."),
        Quote(id: "q056", text: "Me abro a lo que la vida me ofrece hoy."),
        Quote(id: "q057", text: "Confío en que lo correcto llega en el momento correcto."),
        Quote(id: "q058", text: "Sé que la abundancia vive dentro, no fuera."),
        Quote(id: "q059", text: "Soy rico en lo que no se puede contar."),
        Quote(id: "q060", text: "Doy gracias por todo lo que soy y por todo lo que tengo."),

        // Resiliencia / dificultad
        Quote(id: "q061", text: "Ya he superado días difíciles antes, y también superaré este."),
        Quote(id: "q062", text: "Me doblo con la tormenta, y no me rompo."),
        Quote(id: "q063", text: "La dificultad me atraviesa; no me define."),
        Quote(id: "q064", text: "Sigo en pie, y eso ya es una victoria silenciosa."),
        Quote(id: "q065", text: "Cada dificultad me ha enseñado algo que necesitaba saber."),
        Quote(id: "q066", text: "Recibo este desafío con manos firmes y abiertas."),
        Quote(id: "q067", text: "Soy más resistente que mi momento más duro."),
        Quote(id: "q068", text: "Lo que hoy pesa, mañana será más ligero."),
        Quote(id: "q069", text: "Dejo que la dificultad me ablande, no que me endurezca."),
        Quote(id: "q070", text: "Me levanto, con calma y firmeza, tantas veces como haga falta."),

        // Soltar / aceptación
        Quote(id: "q071", text: "Suelto lo que no puedo controlar y conservo mi paz."),
        Quote(id: "q072", text: "Suelto la necesidad de tenerlo todo resuelto."),
        Quote(id: "q073", text: "Aflojo el puño y vuelvo a respirar."),
        Quote(id: "q074", text: "Lo que debe irse, lo dejo ir."),
        Quote(id: "q075", text: "Dejo en el suelo el peso que nunca me tocó cargar."),
        Quote(id: "q076", text: "Hago las paces con los finales y con lo que viene después."),
        Quote(id: "q077", text: "Suelto las viejas historias que ya no me sirven."),
        Quote(id: "q078", text: "Permito que la vida sea incierta y sigo en calma."),
        Quote(id: "q079", text: "Dejo que el río se lleve lo que ya no es mío."),
        Quote(id: "q080", text: "Abro las manos y dejo libre este momento."),

        // Cuerpo / respiración / vitalidad
        Quote(id: "q081", text: "Mi cuerpo es un hogar bueno y fiel."),
        Quote(id: "q082", text: "Respiro hondo y todo mi cuerpo se ablanda."),
        Quote(id: "q083", text: "Doy gracias a mi cuerpo por todo lo que hace en silencio."),
        Quote(id: "q084", text: "La energía me recorre, clara y sin prisa."),
        Quote(id: "q085", text: "Descanso cuando estoy cansado, y confío en que basta."),
        Quote(id: "q086", text: "Trato a mi cuerpo con el cuidado que daría a un amigo."),
        Quote(id: "q087", text: "Cada respiración me llena de una vida serena y firme."),
        Quote(id: "q088", text: "Me siento en casa dentro de mi propia piel."),
        Quote(id: "q089", text: "Recorro mi día con calma y suavidad."),
        Quote(id: "q090", text: "Mi cuerpo y mi mente están del mismo lado tranquilo."),

        // Autocompasión / perdón
        Quote(id: "q091", text: "Me perdono por no saber lo que aún no había aprendido."),
        Quote(id: "q092", text: "Me hablo como le hablaría a alguien que amo."),
        Quote(id: "q093", text: "Tengo permiso para ser un trabajo en proceso."),
        Quote(id: "q094", text: "Suelto al juez severo que llevo dentro y elijo la bondad."),
        Quote(id: "q095", text: "Mis errores son parte de mi crecer, no pruebas en mi contra."),
        Quote(id: "q096", text: "Dejo descansar viejos arrepentimientos y empiezo desde aquí."),
        Quote(id: "q097", text: "Soy amable con las partes de mí que aún sanan."),
        Quote(id: "q098", text: "Merezco la misma compasión que doy con tanta facilidad."),
        Quote(id: "q099", text: "Perdono, para cargar menos y llegar más lejos."),
        Quote(id: "q100", text: "Recibo mi imperfección con el corazón abierto."),

        // Coraje / enfrentar el miedo
        Quote(id: "q101", text: "Puedo sentir miedo y aun así seguir adelante."),
        Quote(id: "q102", text: "El coraje no es la ausencia de miedo; es mi respuesta a él."),
        Quote(id: "q103", text: "Hago lo valiente, un pequeño paso a la vez."),
        Quote(id: "q104", text: "Confío en mí para enfrentar lo que me asusta."),
        Quote(id: "q105", text: "El miedo es una visita; no le dejo gobernar mi casa."),
        Quote(id: "q106", text: "Camino hacia lo que importa, aunque el corazón lata fuerte."),
        Quote(id: "q107", text: "Soy más valiente que ayer."),
        Quote(id: "q108", text: "Dejo que mi coraje sea callado, y aun así me sostiene."),
        Quote(id: "q109", text: "Enfrento este momento con el corazón sereno y abierto."),
        Quote(id: "q110", text: "Elijo crecer antes que la comodidad de quedarme pequeño."),

        // Confianza / entrega
        Quote(id: "q111", text: "Confío en que la vida se despliega como necesita."),
        Quote(id: "q112", text: "Suelto el control y dejo que la vida venga a mi encuentro."),
        Quote(id: "q113", text: "Confío en que el suelo me sostiene, aunque no lo vea."),
        Quote(id: "q114", text: "No necesito ver todo el camino para dar el siguiente paso."),
        Quote(id: "q115", text: "Confío en que lo que necesito me encontrará a tiempo."),
        Quote(id: "q116", text: "Suelto, y aun así estoy sostenido."),
        Quote(id: "q117", text: "Confío en la sabiduría tranquila que vive en mí."),
        Quote(id: "q118", text: "Me apoyo en la vida, y la vida se apoya en mí."),
        Quote(id: "q119", text: "Suelto mis planes con suavidad y me abro a otros mejores."),
        Quote(id: "q120", text: "Algo más grande que mi preocupación me lleva en brazos."),

        // Propósito / contribución
        Quote(id: "q121", text: "Mi vida tiene sentido solo por vivirla bien."),
        Quote(id: "q122", text: "Hoy ofrezco al mundo mi pequeña bondad."),
        Quote(id: "q123", text: "Estoy aquí para crecer, amar y dejar las cosas más suaves."),
        Quote(id: "q124", text: "Mi presencia es un regalo silencioso para quienes me rodean."),
        Quote(id: "q125", text: "Sirvo a la vida al convertirme plenamente en mí mismo."),
        Quote(id: "q126", text: "Hago mi trabajo con cuidado, y dejo que eso baste."),
        Quote(id: "q127", text: "Dejo cada lugar un poco más amable de como lo encontré."),
        Quote(id: "q128", text: "Mi propósito se revela un día honesto a la vez."),
        Quote(id: "q129", text: "Importo, y lo que hago con mis horas importa."),
        Quote(id: "q130", text: "Doy lo que puedo, y confío en que es suficiente."),

        // Alegría / ligereza
        Quote(id: "q131", text: "Me permito disfrutar este día común y hermoso."),
        Quote(id: "q132", text: "La alegría tiene permiso de encontrarme, incluso ahora."),
        Quote(id: "q133", text: "Hago espacio para la risa y la ligereza."),
        Quote(id: "q134", text: "Noto un pequeño deleite y dejo que florezca."),
        Quote(id: "q135", text: "No tengo que ganarme mi propia felicidad."),
        Quote(id: "q136", text: "Dejo que el asombro suavice los bordes de mi día."),
        Quote(id: "q137", text: "Puedo sentirme bien, simplemente porque estoy vivo."),
        Quote(id: "q138", text: "Doy la bienvenida a la alegría sin esperar permiso."),
        Quote(id: "q139", text: "Tomo mi juego tan en serio como mi trabajo."),
        Quote(id: "q140", text: "Dejo que una sonrisa tranquila vuelva a mí."),

        // Claridad / mente quieta
        Quote(id: "q141", text: "Mi mente se aquieta y la claridad surge sola."),
        Quote(id: "q142", text: "Dejo que mis pensamientos se posen como polvo en agua quieta."),
        Quote(id: "q143", text: "No creo cada pensamiento que me atraviesa."),
        Quote(id: "q144", text: "Vuelvo, una y otra vez, a lo que de verdad importa."),
        Quote(id: "q145", text: "Creo espacio entre mis pensamientos y respiro ahí."),
        Quote(id: "q146", text: "Mi mente está clara y mi siguiente paso es sencillo."),
        Quote(id: "q147", text: "Suelto el ruido y escucho la verdad tranquila."),
        Quote(id: "q148", text: "Me concentro en esta sola cosa, con suavidad y plenitud."),
        Quote(id: "q149", text: "Una mente en calma es una mente clara, y estoy en calma."),
        Quote(id: "q150", text: "Confío en las respuestas que llegan en el silencio."),

        // Paciencia / tiempo
        Quote(id: "q151", text: "Confío en el despliegue lento y paciente de mi vida."),
        Quote(id: "q152", text: "Las cosas buenas crecen en su propio tiempo tranquilo."),
        Quote(id: "q153", text: "Soy paciente conmigo y con el camino por delante."),
        Quote(id: "q154", text: "No apuro lo que debe madurar despacio."),
        Quote(id: "q155", text: "Dejo que hoy sea un pequeño paso fiel."),
        Quote(id: "q156", text: "No voy atrasado; llego justo a tiempo."),
        Quote(id: "q157", text: "La paciencia es una forma de amor que me doy."),
        Quote(id: "q158", text: "Hoy siembro semillas y confío en la estación que vendrá."),
        Quote(id: "q159", text: "Avanzo al ritmo de la paz, no al del miedo."),
        Quote(id: "q160", text: "Doy a la vida el tiempo que necesita para florecer."),

        // Valía / suficiencia
        Quote(id: "q161", text: "Soy suficiente, tal como soy, ahora mismo."),
        Quote(id: "q162", text: "No tengo nada que probar ni nada que ganar."),
        Quote(id: "q163", text: "Mi valía no se mide por lo que produzco."),
        Quote(id: "q164", text: "Merezco descanso, alegría y cosas buenas."),
        Quote(id: "q165", text: "Pertenezco aquí, simplemente porque estoy aquí."),
        Quote(id: "q166", text: "No necesito ser perfecto para tener valor."),
        Quote(id: "q167", text: "Estoy completo, incluso los días que me siento a medias."),
        Quote(id: "q168", text: "Me acepto del todo, sin condiciones."),
        Quote(id: "q169", text: "Merezco mi propio tiempo y mi propio cuidado."),
        Quote(id: "q170", text: "Ya soy suficiente, y aún sigo creciendo."),

        // Pertenencia / bondad hacia otros
        Quote(id: "q171", text: "Estoy conectado con cada ser vivo a mi alrededor."),
        Quote(id: "q172", text: "Ofrezco bondad, y vuelve a mí de formas tranquilas."),
        Quote(id: "q173", text: "No estoy solo; soy parte de algo más grande."),
        Quote(id: "q174", text: "Dejo entrar a los demás y me dejo ver."),
        Quote(id: "q175", text: "Recibo a las personas de mi día con el corazón abierto."),
        Quote(id: "q176", text: "Pertenezco, plena y sencillamente, a esta vida compartida."),
        Quote(id: "q177", text: "Doy paciencia a los demás, como la quiero para mí."),
        Quote(id: "q178", text: "Me sostiene una red de bondad invisible."),
        Quote(id: "q179", text: "Veo la lucha callada de otros, y soy amable."),
        Quote(id: "q180", text: "Soy una pequeña luz cálida en el día de alguien."),

        // Sanación / renovación / nuevos comienzos
        Quote(id: "q181", text: "Sano un poco más con cada día que pasa."),
        Quote(id: "q182", text: "Cada mañana me ofrece una página limpia y abierta."),
        Quote(id: "q183", text: "Dejo que lo que me hirió se vuelva lo que me enseña."),
        Quote(id: "q184", text: "Tengo permiso para empezar de nuevo, cuantas veces necesite."),
        Quote(id: "q185", text: "Suelto el ayer y doy la bienvenida a esta nueva luz."),
        Quote(id: "q186", text: "Soy suave con mi sanación; tiene su propio ritmo."),
        Quote(id: "q187", text: "Hago las paces con mi pasado y me vuelvo hacia la mañana."),
        Quote(id: "q188", text: "Me renuevo con el descanso, la respiración y el tiempo."),
        Quote(id: "q189", text: "Las viejas heridas se ablandan cuando las sostengo con cuidado."),
        Quote(id: "q190", text: "Me levanto en este día un poco más entero."),

        // Ecuanimidad / impermanencia (anicca)
        Quote(id: "q191", text: "Todo cambia, y me muevo con suavidad junto al cambio."),
        Quote(id: "q192", text: "Esto también pasará, y yo seguiré aquí, respirando."),
        Quote(id: "q193", text: "Sostengo la alegría y la pena con la misma mano abierta."),
        Quote(id: "q194", text: "Nada permanece; por eso amo este momento mientras está."),
        Quote(id: "q195", text: "Dejo que las emociones suban y bajen como olas, y permanezco."),
        Quote(id: "q196", text: "Soy el agua quieta bajo el clima que pasa."),
        Quote(id: "q197", text: "Acepto el ritmo de llegar y de soltar."),
        Quote(id: "q198", text: "La impermanencia no es pérdida; es la vida en movimiento."),
        Quote(id: "q199", text: "Descanso en la calma que no depende de las condiciones."),
        Quote(id: "q200", text: "Todo fluye, y yo fluyo en paz junto a ello."),
    ]
}

extension LanguagePreference {
    static func detectDefault() -> LanguagePreference {
        let raw = (Locale.preferredLanguages.first ?? "en").lowercased()
        if raw.hasPrefix("ja") { return .ja }
        if raw.hasPrefix("de") { return .de }
        if raw.hasPrefix("fr") { return .fr }
        if raw.hasPrefix("es") { return .es }
        if raw.hasPrefix("pt-br") || raw.hasPrefix("pt_br") { return .ptBR }
        return .en
    }
}
