import org.onegram.ignore.IgnoreRules;
public final class IgnoreRulesSelfTest {
    private static void require(boolean value) { if (!value) throw new AssertionError(); }
    public static void main(String[] args) {
        IgnoreRules.Entry entry = IgnoreRules.begin(null, 100, 1000);
        require(!entry.hides(100, 1000) && entry.hides(101, 1000));
        require(entry.blocksRead() && entry.blocksSend());
        IgnoreRules.Entry preview = entry.preview();
        require(!preview.hides(101, 1000) && preview.blocksRead() && preview.blocksSend());
        require(IgnoreRules.Entry.decode(preview.persisted().encode()).mode == IgnoreRules.HIDDEN);
        IgnoreRules.Entry cancelled = preview.cancel();
        require(cancelled.hides(101, 1000) && cancelled.hides(200, 2000));
        require(cancelled.boundaryId == 100 && cancelled.since == 1000);
        require(IgnoreRules.begin(cancelled, 200, 2000).boundaryId == 100);
        IgnoreRules.Entry restored = IgnoreRules.Entry.decode(cancelled.encode());
        require(restored.hides(101, 1000) && restored.blocksRead());
        IgnoreRules.Entry confirmed = preview.confirm();
        require(!confirmed.blocksRead() && !confirmed.blocksSend() && !confirmed.hides(101, 1000));
        IgnoreRules.Entry emptyChat = IgnoreRules.begin(null, 0, 1000);
        require(!emptyChat.hides(0, 999) && emptyChat.hides(0, 1000));
        System.out.println("Ignore rules: boundary, private preview, cancel, persistence and explicit confirmation passed");
    }
}
