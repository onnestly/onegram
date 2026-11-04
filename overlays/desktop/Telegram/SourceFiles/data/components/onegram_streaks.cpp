#include "data/components/onegram_streaks.h"
#include "data/components/onegram_features.h"

#include "data/components/onegram_streak_rules.h"
#include "data/data_changes.h"
#include "data/data_peer.h"
#include "data/data_user.h"
#include "main/main_session.h"

#include "settings.h"
#include <QtCore/QDateTime>
#include <QtCore/QSettings>
#include <algorithm>
#include <limits>

namespace Data {
namespace {

constexpr auto kPageSize = 32;
constexpr auto kRequestInterval = crl::time(1200);
constexpr auto kRefreshInterval = crl::time(60000);

long long LocalDay(TimeId date) {
	return QDateTime::fromSecsSinceEpoch(date).date().toJulianDay();
}

}  

OneGramStreaks::OneGramStreaks(not_null<Main::Session*> session)
: _session(session)
, _api(&session->mtp())
, _timer([=] { tick(); }) {
	_timer.callEach(kRequestInterval);
}

void OneGramStreaks::reset() {
	++_generation;
	if (_requestId) _api.request(_requestId).cancel();
	_requestId = 0;
	_inFlight = false;
	_pending.clear();
	_focused = nullptr;
	const auto peers = [&] {
		auto result = std::vector<UserData*>();
		for (const auto &[peer, state] : _states) result.push_back(peer);
		return result;
	}();
	_states.clear();
	for (const auto peer : peers) _session->changes().peerUpdated(peer, PeerUpdate::Flag::Name);
}

int OneGramStreaks::count(not_null<PeerData*> peer, bool priority) {
	if (!OneGram::StreaksEnabled(_session)) return 0;
	const auto user = peer->asUser();
	if (priority) {
		_focused = user;
		_focusUntil = crl::now() + 300000;
	}
	if (!user || user->isSelf() || user->isBot()) {
		return 0;
	}
	auto &state = _states[user];
	if (!state.cacheLoaded) {
		state.cacheLoaded = true;
		auto cache = QSettings(cWorkingDir() + u"onegram-streak-days.ini"_q, QSettings::IniFormat);
		cache.beginGroup(QString::number(_session->userId().bare) + u"/"_q + QString::number(user->id.value));
		for (const auto &key : cache.childKeys()) {
			auto valid = false;
			const auto day = key.toLongLong(&valid);
			const auto mask = cache.value(key).toInt();
			if (valid && mask >= 0 && mask <= 3) {
				state.days[day] = state.checked[day] = mask;
				state.covered = std::min(state.covered, day);
			}
		}
		state.result = evaluate(state);
	}
	if (!state.queued
		&& (!state.refreshed
			|| crl::now() - state.refreshed >= kRefreshInterval)) {
		state.queued = true;
		state.offset = 0;
		state.scanDay = QDate::currentDate().toJulianDay();
		state.scanMask = 0;
		state.previousNewest = state.newest;
		state.previousCovered = state.covered;
		state.previousExhausted = state.exhausted;
		state.covered = (1LL << 62);
		state.exhausted = false;
		_pending.push_back(user);
	}
	return state.result;
}

int OneGramStreaks::progress() const {
	if (_pending.empty() && !_inFlight) return -1;
	auto done = 0;
	for (const auto &[user, state] : _states) {
		if (!state.queued && state.result >= 0) ++done;
	}
	return _states.empty() ? 0 : std::min(99, done * 100 / int(_states.size()));
}

bool OneGramStreaks::activeToday(not_null<PeerData*> peer) const {
	const auto user = peer->asUser();
	const auto state = user ? _states.find(user) : _states.end();
	if (state == _states.end()) {
		return false;
	}
	const auto day = state->second.days.find(QDate::currentDate().toJulianDay());
	return day != state->second.days.end() && day->second == 3;
}

int OneGramStreaks::evaluate(const State &state) const {
	return OneGram::CountStreak([&](long long day) {
		const auto i = state.days.find(day);
		return (i == end(state.days)) ? 0 : i->second;
	}, QDate::currentDate().toJulianDay(), state.covered, state.exhausted);
}

void OneGramStreaks::tick() {
	if (_inFlight || _pending.empty()) {
		return;
	}
	const auto focused = (_focused && crl::now() < _focusUntil)
		? std::find_if(_pending.begin(), _pending.end(), [=](const auto &user) {
			return user.get() == _focused;
		})
		: _pending.end();
	const auto next = focused != _pending.end() ? focused : _pending.begin();
	const auto user = *next;
	_pending.erase(next);
	auto &state = _states[user];
	_inFlight = true;
	const auto today = QDate::currentDate().toJulianDay();
	while (state.scanDay < today - 1 && state.checked.contains(state.scanDay)) {
		state.scanMask = state.checked[state.scanDay];
		state.days[state.scanDay] = state.scanMask;
		if (state.scanMask != 3) {
			state.covered = state.scanDay;
			_inFlight = false;
			finish(user, evaluate(state));
			return;
		}
		--state.scanDay;
		state.scanMask = 0;
	}
	const auto end = QDate::fromJulianDay(state.scanDay + 1).startOfDay().toSecsSinceEpoch();
	const auto generation = _generation;
	_requestId = _api.request(MTPmessages_GetHistory(
		user->input(),
		MTP_int(state.offset),
		MTP_int(end),
		MTP_int(0),
		MTP_int(kPageSize),
		MTP_int(0),
		MTP_int(0),
		MTP_long(0)
	)).done([=](const MTPmessages_Messages &result) {
		if (generation != _generation) return;
		_requestId = 0;
		_inFlight = false;
		accept(user, result);
	}).fail([=](const MTP::Error &) {
		if (generation != _generation) return;
		_requestId = 0;
		_inFlight = false;
		finish(user, _states[user].result);
	}).handleFloodErrors().send();
}

void OneGramStreaks::accept(
		not_null<UserData*> user,
		const MTPmessages_Messages &result) {
	auto &state = _states[user];
	auto oldest = std::numeric_limits<TimeId>::max();
	auto offset = state.offset;
	auto size = 0;
	result.match([&](const MTPDmessages_messagesNotModified &) {
	}, [&](const auto &data) {
		size = int(data.vmessages().v.size());
		for (const auto &message : data.vmessages().v) {
			message.match([&](const MTPDmessage &value) {
				const auto id = value.vid().v;
				const auto date = value.vdate().v;
				if (id <= 0 || date <= 0) {
					return;
				}
				offset = offset ? std::min(offset, id) : id;
				oldest = std::min(oldest, TimeId(date));
				state.newest = std::max(state.newest, TimeId(date));
				if (LocalDay(date) == state.scanDay) {
					state.scanMask |= value.is_out() ? 1 : 2;
				}
			}, [&](const MTPDmessageService &value) {
				const auto id = value.vid().v;
				const auto date = value.vdate().v;
				if (id > 0) {
					offset = offset ? std::min(offset, id) : id;
					if (date > 0) {
						oldest = std::min(oldest, TimeId(date));
					}
				}
			}, [&](const MTPDmessageEmpty &value) {
				const auto id = value.vid().v;
				if (id > 0) {
					offset = offset ? std::min(offset, id) : id;
				}
			});
		}
	});
	const auto crossed = !size || (oldest != std::numeric_limits<TimeId>::max()
		&& LocalDay(oldest) < state.scanDay);
	if (state.scanMask != 3 && !crossed && offset != state.offset) {
		state.offset = offset;
		_pending.push_back(user);
		return;
	}
	if (state.scanMask != 3 && !crossed) {
		finish(user, state.result);
		return;
	}
	state.days[state.scanDay] = state.scanMask;
	state.checked[state.scanDay] = state.scanMask;
	{
		auto cache = QSettings(cWorkingDir() + u"onegram-streak-days.ini"_q, QSettings::IniFormat);
		const auto key = QString::number(_session->userId().bare) + u"/"_q + QString::number(user->id.value) + u"/"_q + QString::number(state.scanDay);
		cache.setValue(key, state.scanMask);
	}
	if (state.scanDay == QDate::currentDate().toJulianDay()) {
		_session->changes().peerUpdated(user, PeerUpdate::Flag::Name);
	}

	if (state.scanDay < QDate::currentDate().toJulianDay() && state.scanMask != 3) {
		state.covered = state.scanDay;
		state.exhausted = false;
		finish(user, evaluate(state));
	} else {
		--state.scanDay;
		state.scanMask = 0;
		state.offset = 0;
		_pending.push_back(user);
	}
}

void OneGramStreaks::finish(not_null<UserData*> user, int count) {
	auto &state = _states[user];
	state.queued = false;
	state.refreshed = crl::now();
	const auto active = activeToday(user);
	if (state.result != count || state.lastActive != active) {
		state.result = count;
		state.lastActive = active;
		_session->changes().peerUpdated(user, PeerUpdate::Flag::Name);
	}
}

}  
