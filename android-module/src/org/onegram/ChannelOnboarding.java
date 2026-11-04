package org.onegram;

public final class ChannelOnboarding {
    public interface State {
        boolean opened(long account);
        void remember(long account);
    }
    public interface Open {
        void channel() throws Exception;
    }
    private final State state;
    private final Open open;
    public ChannelOnboarding(State state, Open open) { this.state = state; this.open = open; }
    public boolean accountReady(long account) throws Exception {
        if (account <= 0 || state.opened(account)) return false;
        open.channel();
        state.remember(account);
        return true;
    }
}
