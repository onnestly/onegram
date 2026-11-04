#pragma once

#include "data/components/onegram_ignore_rules.h"
#include "data/data_peer_id.h"
#include <rpl/producer.h>
#include <vector>

class PeerData;
class HistoryItem;
namespace Main { class Session; }

namespace Data::OneGram {

[[nodiscard]] IgnoreEntry IgnoreFor(not_null<PeerData*> peer);
[[nodiscard]] bool IsIgnored(not_null<PeerData*> peer);
[[nodiscard]] bool IsMessageHidden(not_null<HistoryItem*> item);
[[nodiscard]] bool HideIgnoredChats(not_null<Main::Session*> session);
[[nodiscard]] bool StreaksEnabled(not_null<Main::Session*> session);
[[nodiscard]] std::vector<PeerId> IgnoredChats(not_null<Main::Session*> session);
[[nodiscard]] rpl::producer<> FeatureChanges(not_null<Main::Session*> session);

bool BeginIgnore(not_null<PeerData*> peer);
bool PreviewIgnore(not_null<PeerData*> peer);
bool CancelIgnore(not_null<PeerData*> peer);
bool ConfirmIgnore(not_null<PeerData*> peer);
bool SetHideIgnoredChats(not_null<Main::Session*> session, bool enabled);
void RefreshStreaks(not_null<Main::Session*> session);
bool SetStreaksEnabled(not_null<Main::Session*> session, bool enabled);

}  
