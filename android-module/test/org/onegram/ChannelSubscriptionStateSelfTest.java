package org.onegram;

public final class ChannelSubscriptionStateSelfTest {
    public static void main(String[] args) {
        ChannelSubscriptionState state = new ChannelSubscriptionState();
        check(!state.begin(0, false, 1000), "No subscription before login");
        check(state.begin(123, false, 1000), "First account starts");
        check(!state.begin(123, false, 1500), "No duplicate pending request");
        check(state.begin(456, false, 1500), "Second account is independent");
        state.failed(123, 2000);
        check(!state.begin(123, false, 61999), "Failed request cooldown");
        check(state.begin(123, false, 62000), "Failed request can retry");
        state.completed(123);
        check(!state.begin(123, true, 63000), "Persisted success prevents joining after manual leave");
        check(state.begin(456, false, 121500), "Cancelled request cannot block account forever");
        System.out.println("Channel subscription state: auth, per-account isolation, duplicate suppression, failure retry and manual leave passed");
    }
    private static void check(boolean result, String message) {
        if (!result) throw new AssertionError(message);
    }
}
