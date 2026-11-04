package org.onegram.ignore;

import java.util.ArrayList;

public final class IgnoreHooks {
    private static boolean inherits(Class<?> type,String name){for(;type!=null;type=type.getSuperclass())if(type.getName().equals(name))return true;return false;}
    public static boolean hideMessageCell(android.view.View view) {
        try {
            Object message=view.getClass().getMethod("getMessageObject").invoke(view);
            if(message==null)return false;
            int account=((Number)IgnoreStore.field(message,"currentAccount")).intValue();
            IgnoreRules.Entry entry=IgnoreStore.get(account,dialog(message));
            if(entry==null||entry.mode!=IgnoreRules.HIDDEN)return false;
             
            if(!inherits(view.getClass(),"org.telegram.ui.Cells.u1")&&!inherits(view.getClass(),"org.telegram.ui.Cells.x0"))return true;
            Object owner=IgnoreStore.field(message,"messageOwner");
            long id=((Number)IgnoreStore.field(owner,"id")).longValue();
            long date=Integer.toUnsignedLong(((Number)IgnoreStore.field(owner,"date")).intValue());
            return entry.hides(id,date);
        }catch(Exception error){android.util.Log.e("OneGram","Cannot verify message visibility",error);return true;}
    }
    public static boolean hideDialogCell(android.view.View view) {
        if("onegram_ignore_list".equals(view.getTag()))return false;
        try {
            long dialog=((Number)view.getClass().getMethod("getDialogId").invoke(view)).longValue();int account;
            try{account=((Number)IgnoreStore.field(view,"currentAccount")).intValue();}
            catch(Exception ignored){account=((Number)IgnoreStore.field(view,"E0")).intValue();}
            return org.onegram.OneGramConfig.hideIgnored(account)&&IgnoreStore.active(account,dialog);
        }catch(Exception error){android.util.Log.e("OneGram","Cannot verify dialog visibility",error);return true;}
    }
    public static boolean hideThumbnail(Object image) {
        boolean candidate=false;
        try {
            Object parent=image.getClass().getMethod("getParentView").invoke(image);
            if(parent==null||!inherits(parent.getClass(),"org.telegram.ui.Cells.s2"))return false;
            candidate=true;Object[] thumbs=(Object[])IgnoreStore.field(parent,"U1");boolean thumbnail=false;
            for(Object thumb:thumbs)if(thumb==image){thumbnail=true;break;}
            if(!thumbnail)return false;
            long peer=((Number)parent.getClass().getMethod("getDialogId").invoke(parent)).longValue();int account;
            try{account=((Number)IgnoreStore.field(parent,"currentAccount")).intValue();}
            catch(Exception ignored){account=((Number)IgnoreStore.field(parent,"E0")).intValue();}
            return IgnoreStore.active(account,peer);
        }catch(Exception error){android.util.Log.e("OneGram","Cannot verify preview thumbnail",error);return candidate;}
    }
    public static boolean blockRead(Object controller,long dialog) {
        try{return IgnoreStore.active(IgnoreStore.account(controller),dialog);}
        catch(Exception error){android.util.Log.e("OneGram","Cannot verify read-receipt permission",error);return true;}
    }
    public static boolean blockReadTask(Object controller,Object task) {
        try{return blockRead(controller,((Number)IgnoreStore.field(task,"dialogId")).longValue());}
        catch(Exception error){android.util.Log.e("OneGram","Cannot verify queued read receipt",error);return true;}
    }
    public static long dialog(Object message) throws Exception {
        return ((Number)message.getClass().getMethod("getDialogId").invoke(message)).longValue();
    }
    public static boolean blockReadMessage(Object controller,Object message) {
        try{return blockRead(controller,dialog(message));}
        catch(Exception error){android.util.Log.e("OneGram","Cannot verify media receipt",error);return true;}
    }
    public static boolean blockMention(Object controller,int messageId,long channelId,long topicId) {
        if(channelId!=0)return blockRead(controller,-Math.abs(channelId));
        try {
            Object index=IgnoreStore.field(controller,"dialogMessagesByIds");
            Object message=index.getClass().getMethod("get",int.class).invoke(index,messageId);
            if(message!=null)return blockReadMessage(controller,message);
            return !IgnoreStore.entries(IgnoreStore.account(controller)).isEmpty();
        }catch(Exception error){android.util.Log.e("OneGram","Cannot verify mention receipt",error);return true;}
    }
    public static boolean blockSend(Object helper,Object params){
        try{return blockSendPeer(helper,((Number)IgnoreStore.field(params,"peer")).longValue());}
        catch(Exception error){android.util.Log.e("OneGram","Cannot verify message destination",error);return true;}
    }
    public static boolean blockForward(Object helper,Object messages,long peer){return blockSendPeer(helper,peer);}
    private static boolean blockSendPeer(Object helper,long peer){
        try{boolean blocked=IgnoreStore.active(IgnoreStore.account(helper),peer);if(blocked)new android.os.Handler(android.os.Looper.getMainLooper()).post(()->{try{android.widget.Toast.makeText(IgnoreStore.context(),"Подтвердите выход из игнорирования, чтобы отправлять сообщения",android.widget.Toast.LENGTH_LONG).show();}catch(Exception ignored){}});return blocked;}
        catch(Exception error){android.util.Log.e("OneGram","Cannot verify send permission",error);return true;}
    }
    public static void messageAccessibility(android.view.View view,android.view.accessibility.AccessibilityNodeInfo info){
        if(hideMessageCell(view)){info.setVisibleToUser(false);info.setText(null);info.setContentDescription(null);}
    }
    public static void dialogAccessibility(android.view.View view,android.view.accessibility.AccessibilityNodeInfo info){
        try{long peer=((Number)view.getClass().getMethod("getDialogId").invoke(view)).longValue();int account;
            try{account=((Number)IgnoreStore.field(view,"currentAccount")).intValue();}catch(Exception ignored){account=((Number)IgnoreStore.field(view,"E0")).intValue();}
            if(IgnoreStore.active(account,peer)){String name=org.onegram.OneGramUi.dialogName(account,peer);info.setText(name);info.setContentDescription(name+", "+(org.onegram.OneGramUi.russian()?"Чат в игноре":"Chat ignored"));if(org.onegram.OneGramConfig.hideIgnored(account))info.setVisibleToUser(false);}
        }catch(Exception error){info.setText(null);info.setContentDescription(null);}
    }
    public static ArrayList<?> filterNotifications(Object controller,ArrayList<?> messages) {
        ArrayList<Object> visible=new ArrayList<>();
        if(messages==null)return visible;
        try {
            int account=IgnoreStore.account(controller);
            for(Object message:messages)if(!IgnoreStore.active(account,dialog(message)))visible.add(message);
        } catch(Exception error) {
            android.util.Log.e("OneGram","Cannot verify local notification permissions",error);
             
            visible.clear();
        }
        return visible;
    }
    @SuppressWarnings("unchecked")
    public static boolean filterNotificationState(Object controller) {
        try {
            ArrayList<Object> pending=(ArrayList<Object>)IgnoreStore.field(controller,"pushMessages");
            ArrayList<?> allowed=filterNotifications(controller,pending);
            pending.clear();pending.addAll(allowed);
            return true;
        } catch(Exception error) {android.util.Log.e("OneGram","Cannot filter cached notifications",error);return false;}
    }
}
