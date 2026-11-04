package org.onegram;

import java.util.HashMap;
import java.util.Map;

public final class ChannelSubscriptionState {
    private final Map<Long, Long> deadlines = new HashMap<>();

    public boolean begin(long account, boolean completed, long now) {
        if (account <= 0 || completed || now < deadlines.getOrDefault(account, 0L)) return false;
        deadlines.put(account, now + 120000);
        return true;
    }
    public void failed(long account, long now) { deadlines.put(account, now + 60000); }
    public void completed(long account) { deadlines.remove(account); }
}
