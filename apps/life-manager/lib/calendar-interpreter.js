"use strict";

const ONLINE_QUESTION = (when, title) => `${when}の「${title}」、これはオンラインですか？移動時間の計算に使います（次回からは聞きません）。\n［オンライン］［対面］`;
const PLACE_QUESTION = (when, title, place) => `${when}の「${title}」は、いつもの${place}ですか？\n［はい］［別の場所］`;

function norm(value) { return String(value || "").replace(/\s+/g, "").toLowerCase(); }
function selfResponse(event) {
  const self = (event.attendees || []).find((attendee) => attendee && attendee.self);
  return String((self && self.responseStatus) || event.status || "").toLowerCase();
}
function onlineSignal(event) {
  const location = String(event.location || "").trim();
  if (event.online === true || event.isOnline === true
    || /^(?:オンライン|online)(?:\s*$|\s*[:：-]\s*|\s+)/i.test(location)) return true;
  if (location && !/^https?:\/\//i.test(location)) return false;
  const urls = [event.hangoutLink, location]
    .concat(((event.conferenceData || {}).entryPoints || []).map((entry) => entry && entry.uri))
    .filter(Boolean);
  return urls.some((value) => /^https?:\/\//i.test(String(value)));
}
function timezoneOf(event, context) {
  if (event.start && event.start.timeZone) return event.start.timeZone;
  const match = String((event.start || {}).dateTime || "").match(/([+-]\d\d:\d\d)$/);
  return match ? match[1] : (context.timezone || null);
}
function dayLabel(event, context) {
  const raw = (event.start || {}).dateTime || (event.start || {}).date;
  const date = String(raw || "").slice(0, 10);
  const today = String(context.now || new Date().toISOString()).slice(0, 10);
  const atDay = Date.parse(`${date}T00:00:00Z`);
  const nowDay = Date.parse(`${today}T00:00:00Z`);
  const days = Number.isFinite(atDay) && Number.isFinite(nowDay) ? Math.round((atDay - nowDay) / 86400000) : null;
  return days === 1 ? "明日" : Number.isFinite(atDay) ? `${"日月火水木金土"[new Date(atDay).getUTCDay()]}曜` : "次回";
}
function whenLabel(event, context) {
  const day = dayLabel(event, context);
  if (!(event.start || {}).dateTime) return day;
  const match = String(event.start.dateTime).match(/T(\d\d):(\d\d)/);
  return `${day}${match ? `${match[1]}:${match[2]}` : ""}`;
}
function previousOrigin(event, context) {
  const previous = context.previousEvent;
  const start = Date.parse((event.start || {}).dateTime || "");
  const end = Date.parse(((previous || {}).end || {}).dateTime || "");
  const gap = start - end;
  return previous && previous.location && Number.isFinite(gap) && gap >= 0 && gap <= 90 * 60000
    ? previous.location : (context.home || null);
}

function interpretCalendarEvent(event = {}, context = {}) {
  const status = selfResponse(event);
  if (["declined", "tentative", "cancelled", "canceled"].includes(status)) {
    return { decision: "no_call", travel: 0, question: null };
  }
  if ((event.start || {}).date && (event.end || {}).date) {
    return { decision: "no_call", travel: 0, question: null };
  }

  const timezone = timezoneOf(event, context);
  const tz = timezone ? { timezone } : {};
  if (onlineSignal(event)) return { decision: "online", travel: 0, question: null, ...tz };

  const seriesKey = event.recurringEventId || null;
  const series = seriesKey && context.seriesAnswers && context.seriesAnswers[seriesKey];
  if (series) {
    return { decision: series.decision, travel: series.decision === "online" ? 0 : null, question: null,
      ...(series.location ? { location: series.location } : {}), ...tz };
  }

  const title = String(event.summary || "予定").trim();
  const places = context.places || {};
  const remembered = places[title] || places[title.toLowerCase()];
  const rawLocation = String(event.location || remembered || "").trim();
  if (rawLocation) {
    const location = rawLocation;
    if (context.currentLocation && norm(context.currentLocation) === norm(location)) {
      return { decision: "no_call", travel: 0, question: null, location, ...tz };
    }
    const result = { decision: "offline", travel: null, question: null };
    if (remembered) result.location = location;
    const origin = previousOrigin(event, context);
    if (origin) result.origin = origin;
    if (!(event.start || {}).dateTime) {
      const history = (context.history || {})[title];
      if (history && history.startTime) result.startTime = history.startTime;
      else return { decision: "ask_closed", travel: null, question: { type: "time" } };
    }
    return { ...result, ...tz };
  }

  const candidate = (context.candidatePlaces || {})[title];
  if (candidate) return { decision: "ask_closed", travel: null, question: {
    type: "place_confirm", text: PLACE_QUESTION(dayLabel(event, context), title, candidate),
  } };
  const question = { type: "online", text: ONLINE_QUESTION(whenLabel(event, context), title) };
  return { decision: "ask_closed", travel: null, question, ...(seriesKey ? { seriesKey } : {}), ...tz };
}

module.exports = { interpretCalendarEvent, ONLINE_QUESTION, PLACE_QUESTION };
