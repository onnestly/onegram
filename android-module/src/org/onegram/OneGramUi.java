package org.onegram;

import android.app.Activity;
import android.content.*;
import android.graphics.Color;
import android.graphics.drawable.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import android.text.*;
import java.lang.ref.WeakReference;
import java.lang.reflect.*;
import java.util.*;
import org.onegram.ignore.*;

public final class OneGramUi {
    private static final Handler UI=new Handler(Looper.getMainLooper());
    private static WeakReference<Activity> nativeActivity=new WeakReference<>(null);
    private static WeakReference<Object> settingsFragment=new WeakReference<>(null);
    private static WeakReference<Object> fragment=new WeakReference<>(null);
    private static final WeakHashMap<ViewGroup,WeakReference<IgnoreBar>> bars=new WeakHashMap<>();
    private static final WeakHashMap<View,Boolean> ignoredCellFlags=new WeakHashMap<>();
    private static final WeakHashMap<View,StaticLayout> ignoredTimes=new WeakHashMap<>();
    private static final WeakHashMap<View,Mask> masks=new WeakHashMap<>();
    private static final Set<String> chatClasses=new HashSet<>();
    private static long touchedAt,touchedDialog;private static int touchedAccount;
    private static final class Mask {long peer;StaticLayout original,masked,sender;Field senderField,leftField,thumbCountField;int originalLeft,originalThumbCount;}
    public static int selectedAccount(){try{return Class.forName("org.telegram.messenger.UserConfig").getField("selectedAccount").getInt(null);}catch(Exception ignored){return 0;}}
    public static boolean loggedIn(int account){try{return IgnoreStore.owner(account)>0;}catch(Exception error){return false;}}
    public static boolean russian(){
        try{Class<?> type=Class.forName("org.telegram.messenger.LocaleController");Object instance=type.getMethod("getInstance").invoke(null);Object info=type.getMethod("getCurrentLocaleInfo").invoke(instance);return String.valueOf(IgnoreStore.field(info,"shortName")).startsWith("ru");}
        catch(Exception ignored){return Locale.getDefault().getLanguage().equals("ru");}
    }
    private static String l(String ru,String en){return russian()?ru:en;}
    public static void open(Activity context,String screen,int account){context.startActivity(new Intent(context,OneGramActivity.class).putExtra("screen",screen).putExtra("account",account));}
    public static void rememberActivity(Activity activity){nativeActivity=new WeakReference<>(activity);}
    public static void openUpdates(Activity activity){

        Intent intent=new Intent(Intent.ACTION_VIEW,android.net.Uri.parse("tg://resolve?domain=On3Gram"));

        intent.setClassName(activity.getPackageName(),"org.telegram.ui.LaunchActivity");intent.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP|Intent.FLAG_ACTIVITY_CLEAR_TOP);activity.startActivity(intent);

    }

    public static void setProxyEnabled(boolean enabled)throws Exception {
        Context context=IgnoreStore.context();
        if(!OneGramConfig.preferences().edit().putBoolean("proxy_enabled",enabled).commit())throw new java.io.IOException("Cannot persist proxy preference");
        if(enabled){Intent intent=new Intent(context,OneGramService.class).setAction(OneGramService.ACTION_RESUME);context.startForegroundService(intent);}
        else {OneGramBoot.disableProxy(context);context.stopService(new Intent(context,OneGramService.class));}
    }
    public static void checkProxy(Activity activity,TextView status){
        if(!OneGramConfig.proxyEnabled()){status.setText(l("Прокси выключен","Proxy is off"));return;}
        new Thread(()->{String result;try{org.onegram.net.ProxyDiagnostics.check(OneGramConfig.preferences());result=l("Прокси работает","Proxy is working");}catch(Exception error){result=l("Нет ответа от Telegram. Попробуйте ещё раз.","No response from Telegram. Try again.");}
            String value=result;activity.runOnUiThread(()->{if(!activity.isFinishing())status.setText(value);});},"OneGram proxy check").start();
    }
    public static void checkUpdates(Activity activity,int account,TextView version){OneGramUpdates.check(activity,account,version);}
    private static Object controller(int account)throws Exception {return Class.forName("org.telegram.messenger.MessagesController").getMethod("getInstance",int.class).invoke(null,account);}
    private static Object byLong(Object object,String method,long id)throws Exception {
        for(Method candidate:object.getClass().getMethods())if(candidate.getName().equals(method)&&Arrays.equals(candidate.getParameterTypes(),new Class<?>[]{long.class}))return candidate.invoke(object,id);
        throw new NoSuchMethodException(method);
    }
    public static String dialogName(int account,long dialog){
        try{Object object=byLong(controller(account),dialog>0?"getUser":"getChat",Math.abs(dialog));if(dialog<0)return String.valueOf(IgnoreStore.field(object,"title"));String first=String.valueOf(IgnoreStore.field(object,"first_name"));Object last=IgnoreStore.field(object,"last_name");return (first+" "+(last==null?"":last)).trim();}
        catch(Exception error){return l("Чат ","Chat ")+dialog;}
    }
    private static Object dialogObject(int account,long dialog)throws Exception {
        Object index=IgnoreStore.field(controller(account),"dialogs_dict");
        return IgnoreStore.indexValue(index,dialog);
    }
    private static long lastId(int account,long dialog){try{return ((Number)IgnoreStore.field(dialogObject(account,dialog),"top_message")).longValue();}catch(Exception error){return 0;}}
    public static void openChat(Activity activity,int account,long dialog){
        Intent intent=new Intent();intent.setClassName(activity.getPackageName(),"org.telegram.ui.LaunchActivity");
        intent.setAction("com.tmessages.openchat"+System.nanoTime()).putExtra("currentAccount",account);
        if((dialog&0x4000000000000000L)!=0&&dialog>0)intent.putExtra("encId",(int)dialog);
        else if(dialog>0)intent.putExtra("userId",dialog);else intent.putExtra("chatId",-dialog);
        intent.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP|Intent.FLAG_ACTIVITY_CLEAR_TOP);activity.startActivity(intent);
    }
    public static void refresh(int account){
        try{Class<?> type=Class.forName("org.telegram.messenger.NotificationCenter");Object center=type.getMethod("getInstance",int.class).invoke(null,account);Method post=type.getMethod("postNotificationName",int.class,Object[].class);
            post.invoke(center,type.getField("dialogsNeedReload").getInt(null),new Object[0]);post.invoke(center,type.getField("updateInterfaces").getInt(null),new Object[]{0x7fffffff});
        }catch(Exception error){android.util.Log.w("OneGram","Cannot refresh native views",error);}
        Activity activity=nativeActivity.get();if(activity!=null)refreshViews(activity.getWindow().getDecorView());
    }
    private static void refreshViews(View view){view.invalidate();view.requestLayout();if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++)refreshViews(group.getChildAt(i));}}
    public static void trackFragment(Object owner){fragment=new WeakReference<>(owner);UI.post(()->installSettingsEntry(owner));}
    private static long peer(Object owner)throws Exception {
        try{return ((Number)owner.getClass().getMethod("getDialogId").invoke(owner)).longValue();}catch(NoSuchMethodException ignored){}
        Bundle args=(Bundle)owner.getClass().getMethod("getArguments").invoke(owner);if(args==null)return 0;
        Object user=args.get("user_id"),chat=args.get("chat_id"),encrypted=args.get("enc_id");
        if(user instanceof Number)return ((Number)user).longValue();if(chat instanceof Number)return -Math.abs(((Number)chat).longValue());
        if(encrypted instanceof Number)return ((Number)Class.forName("org.telegram.messenger.DialogObject").getMethod("makeEncryptedDialogId",long.class).invoke(null,((Number)encrypted).longValue())).longValue();
        return 0;
    }
    private static Object activeFragment(){
        Object owner=fragment.get();if(owner==null)return null;
        try{Object layout=owner.getClass().getMethod("getParentLayout").invoke(owner);Object top=layout.getClass().getMethod("getLastFragment").invoke(layout);return top==null?owner:top;}catch(Exception ignored){return owner;}
    }
    public static void attachChat(Object owner){
        try{
            chatClasses.add(owner.getClass().getName());
            View view=(View)owner.getClass().getMethod("getFragmentView").invoke(owner);if(!(view instanceof FrameLayout))return;
            long dialog=peer(owner);if(dialog==0)return;int account=((Number)owner.getClass().getMethod("getCurrentAccount").invoke(owner)).intValue();
            FrameLayout parent=(FrameLayout)view;WeakReference<IgnoreBar> reference=bars.get(parent);IgnoreBar existing=reference==null?null:reference.get();
            if(existing==null||existing.dialog!=dialog||existing.account!=account){if(existing!=null)parent.removeView(existing);existing=new IgnoreBar(parent,account,dialog);bars.put(parent,new WeakReference<>(existing));parent.addView(existing,new FrameLayout.LayoutParams(-1,dp(parent,72),Gravity.BOTTOM));}
            existing.update();existing.place();
        }catch(Exception error){android.util.Log.w("OneGram","Cannot attach ignore controls",error);}
    }
    private static int dp(View view,float value){return Math.round(value*view.getResources().getDisplayMetrics().density);}
    private static GradientDrawable rounded(int color,int radius){GradientDrawable drawable=new GradientDrawable();drawable.setColor(color);drawable.setCornerRadius(radius);return drawable;}
    private static TextView action(Context context,String label){TextView text=new TextView(context);text.setText(label);text.setTextSize(16);text.setTextColor(0xff2aabee);text.setGravity(Gravity.CENTER);text.setPadding(16,12,16,12);text.setMinHeight((int)(48*context.getResources().getDisplayMetrics().density));return text;}
    private static final class IgnoreBar extends LinearLayout {
        final int account;final long dialog;final WeakReference<ViewGroup> content;int shown=-1;
        final WeakHashMap<EditText,Boolean> editors=new WeakHashMap<>();
        IgnoreBar(ViewGroup parent,int account,long dialog){super(parent.getContext());this.account=account;this.dialog=dialog;content=new WeakReference<>(parent);setOrientation(VERTICAL);setBackgroundColor(0xff182330);setPadding(dp(this,12),dp(this,4),dp(this,12),dp(this,4));setElevation(dp(this,5));parent.addOnLayoutChangeListener((view,l,t,r,b,ol,ot,or,ob)->place());}
        void place(){ViewGroup root=content.get();if(root==null||getVisibility()==GONE||root.getWidth()==0)return;int height=dp(this,72);measure(MeasureSpec.makeMeasureSpec(root.getWidth(),MeasureSpec.EXACTLY),MeasureSpec.makeMeasureSpec(height,MeasureSpec.EXACTLY));layout(0,Math.max(0,root.getHeight()-height),root.getWidth(),root.getHeight());if(root.indexOfChild(this)!=root.getChildCount()-1)bringToFront();}
        void update()throws Exception {
            IgnoreRules.Entry entry=IgnoreStore.get(account,dialog);int mode=entry==null?IgnoreRules.OFF:entry.mode;
            ViewGroup root=content.get();if(root!=null)editors(root,mode!=IgnoreRules.OFF);
            if(mode==shown)return;shown=mode;setVisibility(mode==IgnoreRules.OFF?GONE:VISIBLE);
            if(mode==IgnoreRules.OFF)return;removeAllViews();
            TextView title=action(getContext(),l("Чат в игноре","Chat ignored"));title.setTextSize(13);title.setTextColor(0xffa8bacb);title.setMinHeight(0);title.setPadding(0,0,0,0);addView(title,new LinearLayout.LayoutParams(-1,dp(this,20)));
            LinearLayout buttons=new LinearLayout(getContext());
            TextView stop=action(getContext(),l("Перестать игнорировать","Stop ignoring"));stop.setOnClickListener(v->stop());buttons.addView(stop,new LinearLayout.LayoutParams(-1,dp(this,44)));
            addView(buttons,new LinearLayout.LayoutParams(-1,dp(this,44)));
        }
        private void editors(View view,boolean disable){
            if(view instanceof EditText){EditText edit=(EditText)view;if(disable){if(!editors.containsKey(edit))editors.put(edit,edit.isEnabled());edit.setEnabled(false);}else{Boolean enabled=editors.remove(edit);if(enabled!=null)edit.setEnabled(enabled);}}
            if(view instanceof ViewGroup&&view!=this){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++)editors(group.getChildAt(i),disable);}
        }
        private void stop(){try{stopIgnoring(account,dialog);update();}catch(Exception error){Toast.makeText(getContext(),l("Не удалось сохранить настройки","Could not save settings"),Toast.LENGTH_LONG).show();}}
    }
    public static void stopIgnoring(int account,long dialog)throws Exception {
        IgnoreRules.Entry entry=IgnoreStore.get(account,dialog);
        if(entry==null||!entry.active())return;
        IgnoreStore.set(account,dialog,entry.confirm());
        refresh(account);
        markRead(account,dialog);
    }
    private static void markRead(int account,long dialog)throws Exception {
        Object controller=controller(account);int max=(int)lastId(account,dialog);
        controller.getClass().getMethod("markDialogAsRead",long.class,int.class,int.class,int.class,boolean.class,long.class,int.class,boolean.class,int.class)
            .invoke(controller,dialog,max,0,(int)(System.currentTimeMillis()/1000),false,0L,0,true,0);
    }
    public static void rememberDialogTouch(View view,android.view.MotionEvent event){
        if(event.getActionMasked()!=android.view.MotionEvent.ACTION_DOWN)return;
        try{touchedDialog=((Number)view.getClass().getMethod("getDialogId").invoke(view)).longValue();try{touchedAccount=((Number)IgnoreStore.field(view,"currentAccount")).intValue();}catch(Exception ignored){touchedAccount=((Number)IgnoreStore.field(view,"E0")).intValue();}touchedAt=SystemClock.elapsedRealtime();}catch(Exception ignored){}
    }
    public static boolean maskDialogPreview(View view){
        try{
            long dialog=((Number)view.getClass().getMethod("getDialogId").invoke(view)).longValue();int account;
            try{account=((Number)IgnoreStore.field(view,"currentAccount")).intValue();}catch(Exception ignored){account=((Number)IgnoreStore.field(view,"E0")).intValue();}
            Field field=IgnoreStore.findField(view,"d3");StaticLayout layout=(StaticLayout)field.get(view);Mask old=masks.get(view);
            if(!IgnoreStore.active(account,dialog)){
                ignoredCellFlags.remove(view);
                if(old!=null&&layout==old.masked){field.set(view,old.original);if(old.senderField!=null)old.senderField.set(view,old.sender);if(old.leftField!=null)old.leftField.setInt(view,old.originalLeft);if(old.thumbCountField!=null)old.thumbCountField.setInt(view,old.originalThumbCount);}
                masks.remove(view);return false;
            }
            ignoredCellFlags.put(view,true);
            suppressIgnoredBadges(view);
            if(layout==null)return true;if(old!=null&&old.peer==dialog&&layout==old.masked){if(old.thumbCountField!=null)old.thumbCountField.setInt(view,0);if(old.senderField!=null)old.senderField.set(view,null);return true;}
            Mask state=new Mask();state.peer=dialog;state.original=layout;
            try{state.senderField=IgnoreStore.findField(view,"r3");state.sender=(StaticLayout)state.senderField.get(view);state.senderField.set(view,null);}catch(NoSuchFieldException ignored){}
            state.thumbCountField=IgnoreStore.findField(view,"Q1");state.originalThumbCount=state.thumbCountField.getInt(view);state.thumbCountField.setInt(view,0);
            state.leftField=IgnoreStore.findField(view,"a3");state.originalLeft=state.leftField.getInt(view);state.leftField.setInt(view,((Number)IgnoreStore.field(view,"w2")).intValue());
            String label=IgnoreStore.preview(account,dialog);
            state.masked=StaticLayout.Builder.obtain(label,0,label.length(),layout.getPaint(),Math.max(1,layout.getWidth()-dp(view,24))).setMaxLines(1).setIncludePad(false).build();field.set(view,state.masked);masks.put(view,state);return true;
        }catch(Exception error){android.util.Log.w("OneGram","Cannot mask chat preview",error);return false;}
    }
    public static void prepareIgnoredCellAfterLayout(View view){if(ignoredCellFlags.containsKey(view))maskDialogPreview(view);}
    public static void suppressIgnoredBadges(View view){
        try{
            long dialog=((Number)view.getClass().getMethod("getDialogId").invoke(view)).longValue();int account=((Number)IgnoreStore.field(view,"E0")).intValue();
            if(!IgnorePresentation.suppressUnread(view))return;
            StaticLayout original=(StaticLayout)IgnoreStore.field(view,"M2");
            if(original!=null&&ignoredTimes.get(view)!=original){long date=IgnoreStore.previewDate(account,dialog);String text=date>0?(String)Class.forName("org.telegram.messenger.LocaleController").getMethod("stringForMessageListDate",long.class).invoke(null,date):"";
                StaticLayout fixed=StaticLayout.Builder.obtain(text,0,text.length(),original.getPaint(),Math.max(1,original.getWidth())).setMaxLines(1).setIncludePad(false).build();IgnoreStore.findField(view,"M2").set(view,fixed);ignoredTimes.put(view,fixed);}
        }catch(Exception error){android.util.Log.w("OneGram","Cannot suppress ignored chat counters",error);}
    }
    private static boolean isSettings(){
        Object owner=activeFragment();if(owner==null)return false;if(owner==settingsFragment.get())return true;
        try{Object bar=owner.getClass().getMethod("getActionBar").invoke(owner);String title=String.valueOf(bar.getClass().getMethod("getTitle").invoke(bar));boolean match=title.equals("Settings")||title.equals("Настройки");if(match)settingsFragment=new WeakReference<>(owner);return match;}catch(Exception error){return false;}
    }
    private static void installSettingsEntry(Object owner){
        try{if(isSettings()){View root=(View)owner.getClass().getMethod("getFragmentView").invoke(owner);if(root!=null)root.requestLayout();}}catch(Exception ignored){}
    }
     
    public static int settingsHeaderExtra(View view){
        try{
            String title=String.valueOf(view.getClass().getMethod("getText").invoke(view));
            boolean match=isSettings()&&(title.equals("Account")||title.equals("Аккаунт"));
            FrameLayout parent=(FrameLayout)view;View old=parent.findViewWithTag("onegram_settings_entry");
            if(!match){if(old!=null)parent.removeView(old);return 0;}
            if(old==null){old=nativeAction(view.getContext(),l("Настройки OneGram","OneGram Settings"),"msg_settings");old.setTag("onegram_settings_entry");old.setOnClickListener(v->{Activity activity=nativeActivity.get();if(activity!=null)open(activity,"settings",selectedAccount());});parent.addView(old,new FrameLayout.LayoutParams(-1,dp(view,56)));}
            old.measure(View.MeasureSpec.makeMeasureSpec(view.getMeasuredWidth(),View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(dp(view,56),View.MeasureSpec.EXACTLY));
            return dp(view,56);
        }catch(Exception error){android.util.Log.e("OneGram","Cannot attach native settings row",error);return 0;}
    }
    public static void layoutSettingsHeader(View view){
        int extra=settingsHeaderExtra(view);if(extra==0)return;
        ViewGroup parent=(ViewGroup)view;for(int i=0;i<parent.getChildCount();i++){View child=parent.getChildAt(i);if("onegram_settings_entry".equals(child.getTag()))child.layout(0,0,parent.getWidth(),extra);else child.offsetTopAndBottom(extra);}
    }
    public static View nativeAction(Context context,String label,String icon){
        try{
            Class<?> type=Class.forName("org.telegram.ui.Cells.ca");View cell=(View)type.getConstructor(Context.class).newInstance(context);
            type.getMethod("b",CharSequence.class,boolean.class).invoke(cell,label,false);
            int resource=context.getResources().getIdentifier(icon,"drawable",context.getPackageName());
            if(resource!=0)type.getMethod("setIcon",int.class).invoke(cell,resource);
            return cell;
        }catch(Exception error){
            TextView item=new TextView(context);item.setText(label);item.setTextSize(16);item.setTextColor(0xffe9edf1);item.setGravity(Gravity.CENTER_VERTICAL|Gravity.START);item.setPadding(dp(item,20),0,dp(item,20),0);int resource=context.getResources().getIdentifier(icon,"drawable",context.getPackageName());if(resource!=0){android.graphics.drawable.Drawable drawable=context.getDrawable(resource).mutate();drawable.setTint(0xffa8b2bd);drawable.setBounds(0,0,dp(item,24),dp(item,24));item.setCompoundDrawables(drawable,null,null,null);item.setCompoundDrawablePadding(dp(item,20));}return item;
        }
    }
    public static View ignoredRow(Activity activity,int account,long dialog)throws Exception {
        Class<?> type=Class.forName("org.telegram.ui.Cells.s2");View cell=(View)type.getConstructor(Context.class,boolean.class).newInstance(activity,false);cell.setTag("onegram_ignore_list");
        Object data=dialogObject(account,dialog);
        if(data!=null)type.getMethod("X",Class.forName("org.telegram.tgnet.TLRPC$Dialog"),int.class,int.class).invoke(cell,data,0,0);
        else type.getMethod("setCurrentDialogId",long.class).invoke(cell,dialog);
        return cell;
    }
    private static View findRecycler(View view){try{view.getClass().getMethod("getLayoutManager");return view;}catch(Exception ignored){}if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View child=findRecycler(group.getChildAt(i));if(child!=null)return child;}}return null;}
    public static void decorateMenu(PopupWindow popup){
        View root=popup.getContentView();if(root==null)return;
        for(String tag:new String[]{"onegram_ignore_action","onegram_ignored_chats","onegram_menu_settings"}){View previous=root.findViewWithTag(tag);if(previous!=null&&previous.getParent() instanceof ViewGroup)((ViewGroup)previous.getParent()).removeView(previous);}
        ArrayList<View> labels=new ArrayList<>();collectLabels(root,labels);View saved=null,block=null,leave=null;boolean messageMenu=false;
        for(View view:labels){String text=label(view).trim();if(text.equals("Избранное")||text.equals("Saved Messages"))saved=view;if(text.equals("Заблокировать")||text.equals("Block User")||text.equals("Block user")||text.equals("Разблокировать")||text.equals("Unblock"))block=view;if(text.toLowerCase(java.util.Locale.ROOT).contains("покинуть")||text.toLowerCase(java.util.Locale.ROOT).contains("выйти")||text.toLowerCase(java.util.Locale.ROOT).contains("leave "))leave=view;if(text.equals("Ответить")||text.equals("Reply"))messageMenu=true;}
        Activity activity=nativeActivity.get();if(activity==null)return;
        if(saved!=null){insertMenu(saved,l("Настройки OneGram","OneGram Settings"),"onegram_menu_settings",()->open(activity,"settings",selectedAccount()));insertMenu(saved,l("Чаты в игноре","Ignored Chats"),"onegram_ignored_chats",()->open(activity,"ignored",selectedAccount()));popup.setHeight(-2);return;}
        if(messageMenu||block==null&&leave==null)return;
        try{
            Object owner=activeFragment();long dialog=0;int account=selectedAccount();
            if(owner!=null&&(owner.getClass().getName().equals("org.telegram.ui.ProfileActivity")||chatClasses.contains(owner.getClass().getName()))){dialog=peer(owner);account=((Number)owner.getClass().getMethod("getCurrentAccount").invoke(owner)).intValue();}
            else if(SystemClock.elapsedRealtime()-touchedAt<3500){dialog=touchedDialog;account=touchedAccount;}
            if(dialog==0||dialog==IgnoreStore.owner(account))return;
            final long selected=dialog;final int slot=account;boolean active=IgnoreStore.active(slot,selected);View anchor=block!=null?block:leave;
            insertMenu(anchor,active?l("Перестать игнорировать","Stop ignoring"):l("Игнорировать","Ignore"),"onegram_ignore_action",()->{
                try{IgnoreRules.Entry entry=IgnoreStore.get(slot,selected);boolean was=entry!=null&&entry.active();if(was)stopIgnoring(slot,selected);else IgnoreStore.set(slot,selected,IgnoreRules.begin(null,lastId(slot,selected),System.currentTimeMillis()/1000));
                    Object notifications=Class.forName("org.telegram.messenger.NotificationsController").getMethod("getInstance",int.class).invoke(null,slot);notifications.getClass().getMethod("removeNotificationsForDialog",long.class).invoke(notifications,selected);
                    refresh(slot);if(was)openChat(activity,slot,selected);
                }catch(Exception error){Toast.makeText(activity,l("Не удалось сохранить настройки","Could not save settings"),Toast.LENGTH_LONG).show();}
            });popup.setHeight(-2);
        }catch(Exception error){android.util.Log.w("OneGram","Cannot decorate peer menu",error);}
    }
    private static boolean hasMethod(Object object,String name){for(Method method:object.getClass().getMethods())if(method.getName().equals(name))return true;return false;}
    private static String label(View view){try{Object text=view.getClass().getMethod("getText").invoke(view);return text==null?"":text.toString();}catch(Exception error){return "";}}
    private static void collectLabels(View view,List<View> result){if(!label(view).isEmpty())result.add(view);if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++)collectLabels(group.getChildAt(i),result);}}
    private static void insertMenu(View anchor,String label,String tag,Runnable action){
        View row=anchor;while(row.getParent() instanceof ViewGroup){ViewGroup parent=(ViewGroup)row.getParent();if(parent instanceof LinearLayout&&((LinearLayout)parent).getOrientation()==LinearLayout.VERTICAL){View item=nativeAction(parent.getContext(),label,tag.equals("onegram_menu_settings")?"msg_settings":tag.equals("onegram_ignored_chats")?"msg_archive":"msg_block");
                item.setTag(tag);item.setOnClickListener(v->{View window=item.getRootView();window.dispatchKeyEvent(new KeyEvent(KeyEvent.ACTION_DOWN,KeyEvent.KEYCODE_BACK));window.dispatchKeyEvent(new KeyEvent(KeyEvent.ACTION_UP,KeyEvent.KEYCODE_BACK));action.run();});parent.addView(item,parent.indexOfChild(row)+1,new LinearLayout.LayoutParams(-1,dp(item,48)));return;}row=parent;}
    }
}
