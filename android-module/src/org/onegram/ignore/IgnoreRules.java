package org.onegram.ignore;

public final class IgnoreRules {
    public static final int OFF = 0, HIDDEN = 1, PREVIEW = 2;
    public static final class Entry {
        public final int mode;
        public final long boundaryId, since;
        public Entry(int mode, long boundaryId, long since) {
            if (mode < OFF || mode > PREVIEW || boundaryId < 0 || since < 0) throw new IllegalArgumentException();
            this.mode = mode; this.boundaryId = boundaryId; this.since = since;
        }
        public boolean active() { return mode != OFF; }
        public boolean blocksRead() { return active(); }
        public boolean blocksSend() { return active(); }
        public boolean hides(long id, long date) {
            return mode == HIDDEN && (boundaryId > 0 ? id > boundaryId : date >= since);
        }
        public Entry preview() { return active() ? new Entry(PREVIEW, boundaryId, since) : this; }
        public Entry cancel() { return active() ? new Entry(HIDDEN, boundaryId, since) : this; }
        public Entry confirm() { return new Entry(OFF, boundaryId, since); }
        public Entry persisted() { return mode == PREVIEW ? cancel() : this; }
        public String encode() { return mode + ":" + boundaryId + ":" + since; }
        public static Entry decode(String value) {
            String[] parts = value.split(":", -1);
            if (parts.length != 3) throw new IllegalArgumentException();
            return new Entry(Integer.parseInt(parts[0]), Long.parseLong(parts[1]), Long.parseLong(parts[2]));
        }
    }
    public static Entry begin(Entry existing, long boundaryId, long since) {
        return existing != null && existing.active() ? existing : new Entry(HIDDEN, Math.max(0, boundaryId), since);
    }
}
