#include "data/components/onegram_features.h"
#include "data/components/onegram_streaks.h"

#include "core/application.h"
#include "data/data_changes.h"
#include "data/data_histories.h"
#include "data/data_peer.h"
#include "data/data_session.h"
#include "history/history.h"
#include "history/history_item.h"
#include "history/view/history_view_element.h"
#include "main/main_session.h"
#include "settings.h"
#include "window/notifications_manager.h"

#include <QtCore/QDateTime>
#include <QtCore/QSettings>
#include <rpl/event_stream.h>
#include <map>
#include <memory>

namespace Data::OneGram {
namespace {

struct Features {
	std::map<quint64, IgnoreEntry> ignored;
	rpl::event_stream<> changes;
	bool hideIgnored = false;
	bool streaks = true;
};

auto &Registry() {
	static const auto result = new std::map<Main::Session*, std::unique_ptr<Features>>();
	return *result;
}

QSettings Preferences(not_null<Main::Session*> session) {
	return QSettings(cWorkingDir() + u"onegram-features.ini"_q, QSettings::IniFormat);
}

QString AccountGroup(not_null<Main::Session*> session) {
	return u"accounts/%1"_q.arg(session->userId().bare);
}

Features &State(not_null<Main::Session*> session) {
	auto &entry = Registry()[session.get()];
	if (entry) return *entry;
	entry = std::make_unique<Features>();
	auto preferences = Preferences(session);
	preferences.beginGroup(AccountGroup(session));
	entry->hideIgnored = preferences.value(u"hide_ignored"_q, false).toBool();
	entry->streaks = preferences.value(u"streaks"_q, true).toBool();
	preferences.beginGroup(u"ignored"_q);
	for (const auto &key : preferences.childGroups()) {
		auto valid = false;
		const auto id = key.toULongLong(&valid);
		if (!valid || !id) continue;
		preferences.beginGroup(key);
		entry->ignored[id] = {
			IgnoreMode::Hidden,
			preferences.value(u"boundary"_q, 0).toLongLong(),
			preferences.value(u"since"_q, 0).toLongLong(),
		};
		preferences.endGroup();
	}
	session->lifetime().add([session] { Registry().erase(session.get()); });
	return *entry;
}

void Refresh(not_null<PeerData*> peer) {
	auto &session = peer->session();
	if (const auto history = session.data().historyLoaded(peer)) {
		Core::App().notifications().clearIncomingFromHistory(history);
		for (const auto &block : history->blocks) {
			for (const auto &view : block->messages) {
				session.data().requestViewResize(view.get());
			}
		}
		history->updateChatListExistence();
		history->updateChatListEntry();
		session.data().notifyHistoryChangeDelayed(history);
	}
	session.changes().peerUpdated(peer, PeerUpdate::Flag::Name);
	State(&session).changes.fire({});
}

bool Write(not_null<PeerData*> peer, IgnoreEntry value) {
	auto &session = peer->session();
	auto preferences = Preferences(&session);
	preferences.beginGroup(AccountGroup(&session));
	preferences.beginGroup(u"ignored/%1"_q.arg(peer->id.value));
	if (value.active()) {
		preferences.setValue(u"mode"_q, 1);
		preferences.setValue(u"boundary"_q, value.boundaryId);
		preferences.setValue(u"since"_q, value.since);
	} else {
		preferences.remove(QString());
	}
	preferences.sync();
	if (preferences.status() != QSettings::NoError) return false;
	auto &state = State(&session);
	if (value.active()) state.ignored[peer->id.value] = value;
	else state.ignored.erase(peer->id.value);
	Refresh(peer);
	return true;
}

}  

IgnoreEntry IgnoreFor(not_null<PeerData*> peer) {
	const auto &states = State(&peer->session()).ignored;
	const auto found = states.find(peer->id.value);
	return found == states.end() ? IgnoreEntry() : found->second;
}

bool IsIgnored(not_null<PeerData*> peer) {
	return IgnoreFor(peer).active();
}

bool IsMessageHidden(not_null<HistoryItem*> item) {
	return IgnoreFor(item->history()->peer).hides(item->id.bare, item->date());
}

bool HideIgnoredChats(not_null<Main::Session*> session) {
	return State(session).hideIgnored;
}

bool StreaksEnabled(not_null<Main::Session*> session) {
	return State(session).streaks;
}

std::vector<PeerId> IgnoredChats(not_null<Main::Session*> session) {
	auto result = std::vector<PeerId>();
	for (const auto &[id, entry] : State(session).ignored) {
		if (entry.active()) result.push_back(PeerId(uint64(id)));
	}
	return result;
}

rpl::producer<> FeatureChanges(not_null<Main::Session*> session) {
	return State(session).changes.events();
}

bool BeginIgnore(not_null<PeerData*> peer) {
	const auto history = peer->session().data().history(peer);
	const auto last = history->lastServerMessage();
	return Write(peer, Data::OneGram::BeginIgnore(
		IgnoreFor(peer), last ? last->id.bare : 0, QDateTime::currentSecsSinceEpoch()));
}

bool PreviewIgnore(not_null<PeerData*> peer) {
	return Write(peer, IgnoreFor(peer).preview());
}

bool CancelIgnore(not_null<PeerData*> peer) {
	return Write(peer, IgnoreFor(peer).cancel());
}

bool ConfirmIgnore(not_null<PeerData*> peer) {
	if (!Write(peer, IgnoreFor(peer).confirm())) return false;
	peer->session().data().histories().readInbox(peer->session().data().history(peer));
	return true;
}

bool SetHideIgnoredChats(not_null<Main::Session*> session, bool enabled) {
	auto preferences = Preferences(session);
	preferences.setValue(AccountGroup(session) + u"/hide_ignored"_q, enabled);
	preferences.sync();
	if (preferences.status() != QSettings::NoError) return false;
	State(session).hideIgnored = enabled;
	for (const auto id : IgnoredChats(session)) {
		if (const auto peer = session->data().peerLoaded(id)) Refresh(peer);
	}
	return true;
}

void RefreshStreaks(not_null<Main::Session*> session) {
	auto cache = QSettings(cWorkingDir() + u"onegram-streak-days.ini"_q, QSettings::IniFormat);
	cache.remove(QString::number(session->userId().bare));
	cache.sync();
	session->onegramStreaks().reset();
	State(session).changes.fire({});
}

bool SetStreaksEnabled(not_null<Main::Session*> session, bool enabled) {
	auto preferences = Preferences(session);
	preferences.setValue(AccountGroup(session) + u"/streaks"_q, enabled);
	preferences.sync();
	if (preferences.status() != QSettings::NoError) return false;
	State(session).streaks = enabled;
	session->onegramStreaks().reset();
	State(session).changes.fire({});
	return true;
}

}  
