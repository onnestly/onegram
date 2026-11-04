#pragma once

#include "base/timer.h"
#include "mtproto/sender.h"

#include <deque>
#include <map>

class PeerData;
class UserData;

namespace Main {
class Session;
}  

namespace Data {

class OneGramStreaks final {
public:
	explicit OneGramStreaks(not_null<Main::Session*> session);
	void reset();
	[[nodiscard]] int count(not_null<PeerData*> peer, bool priority = false);
	[[nodiscard]] int progress() const;
	[[nodiscard]] bool activeToday(not_null<PeerData*> peer) const;

private:
	struct State {
		std::map<long long, int> days;
		long long covered = (1LL << 62);
		long long previousCovered = (1LL << 62);
		TimeId newest = 0;
		TimeId previousNewest = 0;
		crl::time refreshed = 0;
		int offset = 0;
		long long scanDay = 0;
		int scanMask = 0;
		std::map<long long, int> checked;
		int result = -1;
		bool exhausted = false;
		bool previousExhausted = false;
		bool queued = false;
		bool lastActive = false;
		bool cacheLoaded = false;
	};

	void tick();
	void accept(not_null<UserData*> user, const MTPmessages_Messages &result);
	void finish(not_null<UserData*> user, int count);
	[[nodiscard]] int evaluate(const State &state) const;

	const not_null<Main::Session*> _session;
	MTP::Sender _api;
	std::map<UserData*, State> _states;
	std::deque<not_null<UserData*>> _pending;
	bool _inFlight = false;
	mtpRequestId _requestId = 0;
	int _generation = 0;
	UserData *_focused = nullptr;
	crl::time _focusUntil = 0;
	base::Timer _timer;

};

}  
