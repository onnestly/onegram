package org.onegram;
import java.util.*;

public final class ChannelOnboardingSelfTest {
    public static void main(String[] args) throws Exception {
        Set<Long> seen = new HashSet<>();
        List<String> events = new ArrayList<>();
        ChannelOnboarding.State state = new ChannelOnboarding.State() {
            public boolean opened(long id) { return seen.contains(id); }
            public void remember(long id) { events.add("remember:" + id); seen.add(id); }
        };
        ChannelOnboarding flow = new ChannelOnboarding(state, () -> events.add("open"));
        if (flow.accountReady(0) || !events.isEmpty()) throw new AssertionError("Opened before login");
        if (!flow.accountReady(123) || !events.equals(Arrays.asList("open", "remember:123"))) throw new AssertionError("Login did not open first");
        if (flow.accountReady(123) || events.size() != 2) throw new AssertionError("Repeated opening on resume");
        if (!flow.accountReady(456) || !seen.contains(456L)) throw new AssertionError("Second account skipped");
        ChannelOnboarding failing = new ChannelOnboarding(state, () -> { throw new Exception("Cannot open"); });
        try { failing.accountReady(789); throw new AssertionError("Expected failure"); } catch (Exception expected) {}
        if (seen.contains(789L)) throw new AssertionError("Failed opening was marked complete");
        if (!flow.accountReady(789)) throw new AssertionError("Retry was skipped");
        System.out.println("Channel onboarding: login transition, per-account once-only state, and failed-open retry passed");
    }
}
