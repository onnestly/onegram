package org.onegram;

import android.app.Activity;
import android.content.*;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.*;
import android.os.Bundle;
import android.view.*;
import android.widget.*;
import org.json.JSONObject;
import org.onegram.ignore.*;
import java.util.Map;

public final class OneGramScreen extends FrameLayout {
    private final Activity host;
    private final Runnable close;
    private int BG=0xff17212b, CARD=0xff1f2c3a, TEXT=0xffe9edf1, MUTED=0xffa8bacb, ACCENT=0xff6ab3f3;
    private LinearLayout root,body,footer;
    private String screen;
    private int account;

    private int dp(float value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private String l(String ru,String en){return OneGramUi.russian()?ru:en;}
    public OneGramScreen(Activity host,String screen,int account,Runnable close){
        super(host);this.host=host;this.close=close;this.screen=screen;this.account=account;
        try{View nativeCell=OneGramUi.nativeAction(host,"","msg_settings");TextView nativeText=(TextView)nativeCell.getClass().getMethod("getTextView").invoke(nativeCell);TEXT=nativeText.getCurrentTextColor();if(Color.luminance(TEXT)<0.5){BG="ignored".equals(screen)?Color.WHITE:0xfff1f1f1;CARD=Color.WHITE;MUTED=0xff8a8a8a;ACCENT=0xff168acd;}}catch(Exception ignored){}
        setBackgroundColor(BG);
        render();
    }
    public int surfaceColor(){return BG;}
    public boolean lightTheme(){return Color.luminance(TEXT)<0.5;}
    public void refresh(){if("ignored".equals(screen))render();}
    private TextView text(String value,int size,int color,boolean bold){
        TextView view=new TextView(host);view.setText(value);view.setTextSize(size);view.setTextColor(color);
        view.setTypeface(Typeface.create("sans-serif"+(bold?"-medium":""),Typeface.NORMAL));
        view.setLineSpacing(dp(3),1);return view;
    }
    private GradientDrawable shape(int color,int radius){GradientDrawable result=new GradientDrawable();result.setColor(color);result.setCornerRadius(dp(radius));return result;}
    private TextView button(String label,boolean primary,View.OnClickListener action){
        TextView button=text(label,16,primary?Color.WHITE:TEXT,primary);button.setGravity(Gravity.CENTER);
        button.setBackground(new RippleDrawable(android.content.res.ColorStateList.valueOf(0x25ffffff),shape(primary?ACCENT:CARD,12),null));
        if(!primary){button.setGravity(Gravity.CENTER_VERTICAL|Gravity.START);String icon=label.contains("Версия")||label.startsWith("Version")?"msg_info":label.contains("Чаты")||label.equals("Ignored Chats")?"msg_archive":"msg_retry";int resource=getResources().getIdentifier(icon,"drawable",host.getPackageName());if(resource!=0){Drawable drawable=host.getDrawable(resource).mutate();drawable.setTint(MUTED);drawable.setBounds(0,0,dp(24),dp(24));button.setCompoundDrawables(drawable,null,null,null);button.setCompoundDrawablePadding(dp(20));}}
        button.setPadding(dp(20),0,dp(20),0);button.setOnClickListener(action);button.setFocusable(true);button.setMinHeight(dp(52));return button;
    }
    private void space(LinearLayout parent,int height){View view=new View(host);parent.addView(view,new LinearLayout.LayoutParams(1,dp(height)));}
    private void base(String title,boolean back){
        root=new LinearLayout(host);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(BG);
        int horizontal="ignored".equals(screen)?0:dp(24);root.setPadding(horizontal,0,horizontal,dp(16));
        
        root.setOnApplyWindowInsetsListener((view,insets)->{view.setPadding(horizontal,insets.getSystemWindowInsetTop(),horizontal,dp(16)+insets.getSystemWindowInsetBottom());return insets;});
        LinearLayout bar=new LinearLayout(host);bar.setGravity(Gravity.CENTER_VERTICAL);
        if(back){TextView arrow=text("‹",34,ACCENT,false);arrow.setGravity(Gravity.CENTER);arrow.setContentDescription(l("Назад","Back"));arrow.setOnClickListener(v->close.run());bar.addView(arrow,new LinearLayout.LayoutParams(dp(36),dp(56)));}
        TextView heading=text(title,20,TEXT,true);bar.addView(heading,new LinearLayout.LayoutParams(0,dp(56),1));heading.setGravity(Gravity.CENTER_VERTICAL);
        root.addView(bar);
        ScrollView scroll=new ScrollView(host);scroll.setFillViewport(true);scroll.setClipToPadding(false);
        body=new LinearLayout(host);body.setOrientation(LinearLayout.VERTICAL);body.setPadding(0,dp(20),0,dp(24));
        scroll.addView(body,new ScrollView.LayoutParams(-1,-2));root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        footer=new LinearLayout(host);footer.setOrientation(LinearLayout.VERTICAL);root.addView(footer,new LinearLayout.LayoutParams(-1,-2));
        removeAllViews();addView(root,new FrameLayout.LayoutParams(-1,-1));
    }
    private void title(String value){body.addView(text(value,30,TEXT,true));space(body,16);}
    private void paragraph(String value){body.addView(text(value,17,MUTED,false));space(body,24);}
    private void render(){if("ignored".equals(screen))ignored();else settings();}
    private interface Change {void set(boolean value)throws Exception;}
    private void toggle(String label,boolean checked,Change change){
        Switch row=new Switch(host);row.setText(label);row.setTextSize(16);row.setTextColor(TEXT);row.setPadding(dp(16),dp(12),dp(16),dp(12));row.setMinHeight(dp(60));row.setBackground(shape(CARD,12));row.setChecked(checked);row.setThumbTintList(android.content.res.ColorStateList.valueOf(Color.WHITE));row.setTrackTintList(new android.content.res.ColorStateList(new int[][]{new int[]{android.R.attr.state_checked},new int[]{}},new int[]{0xaa2aabee,0xff425466}));
        row.setOnCheckedChangeListener((button,value)->{try{change.set(value);}catch(Exception error){button.setOnCheckedChangeListener(null);button.setChecked(!value);toast(l("Не удалось сохранить настройки","Could not save settings"));render();}});
        body.addView(row,new LinearLayout.LayoutParams(-1,-2));space(body,12);
    }
    private void section(String value){space(body,16);TextView label=text(value,15,ACCENT,true);label.setPadding(0,0,0,dp(12));body.addView(label);}
    private void settings(){
        base(l("Настройки OneGram","OneGram Settings"),true);
        section(l("Прокси","Proxy"));toggle(l("Использовать прокси","Use proxy"),OneGramConfig.proxyEnabled(),value->OneGramUi.setProxyEnabled(value));
        TextView status=text("",14,MUTED,false);TextView check=button(l("Проверить","Check"),false,v->{status.setText(l("Проверка…","Checking…"));OneGramUi.checkProxy(host,status);});body.addView(check,new LinearLayout.LayoutParams(-1,dp(48)));body.addView(status);
        section(l("Игнорирование","Ignore"));toggle(l("Убирать из списка чатов","Hide from chat list"),OneGramConfig.hideIgnored(account),value->{if(!OneGramConfig.setHideIgnored(account,value))throw new java.io.IOException();OneGramUi.refresh(account);});
        paragraph(l("Скрытые чаты доступны в меню ⋮ → «Чаты в игноре».","Open the ⋮ menu > Ignored Chats to find hidden chats."));
        body.addView(button(l("Чаты в игноре","Ignored Chats"),false,v->OneGramUi.open(host,"ignored",account)),new LinearLayout.LayoutParams(-1,dp(48)));
        section(l("Огоньки","Streaks"));toggle(l("Показывать огоньки","Show streaks"),OneGramConfig.showStreaks(account),value->{if(!OneGramConfig.setShowStreaks(account,value))throw new java.io.IOException();org.onegram.streak.StreakUi.preferencesChanged();OneGramUi.refresh(account);});
        body.addView(button(l("Обновить","Recalculate"),false,v->{org.onegram.streak.StreakUi.recalculate(account);toast(l("Пересчитываем ваши огоньки","Recalculating your streaks"));}),new LinearLayout.LayoutParams(-1,dp(48)));
        section(l("Обновления","Updates"));TextView version=button(l("Версия ","Version ")+OneGramConfig.VERSION+" · "+l("Проверить","Check"),false,null);version.setOnClickListener(v->OneGramUi.checkUpdates(host,account,version));body.addView(version,new LinearLayout.LayoutParams(-1,dp(52)));
    }
    private void ignored(){
        base(l("Чаты в игноре","Ignored Chats"),true);body.setPadding(0,0,0,0);
        try {
            Map<Long,IgnoreRules.Entry> entries=IgnoreStore.entries(account);
            if(entries.isEmpty()){paragraph(l("Здесь появятся чаты, которые вы игнорируете.","Chats you ignore will appear here."));return;}
            for(Map.Entry<Long,IgnoreRules.Entry> row:entries.entrySet()){
                long dialog=row.getKey();View item=OneGramUi.ignoredRow(host,account,dialog);
                item.setOnClickListener(v->{OneGramUi.openChat(host,account,dialog);close.run();});
                item.setOnLongClickListener(v->{new android.app.AlertDialog.Builder(host).setTitle(OneGramUi.dialogName(account,dialog)).setItems(new String[]{l("Перестать игнорировать","Stop ignoring")},(d,index)->{try{OneGramUi.stopIgnoring(account,dialog);OneGramUi.openChat(host,account,dialog);close.run();}catch(Exception error){toast(l("Не удалось сохранить настройки","Could not save settings"));}}).show();return true;});
                body.addView(item,new LinearLayout.LayoutParams(-1,-2));
            }
        }catch(Exception error){paragraph(l("Не удалось загрузить список","Could not load ignored chats"));}
    }
    private void toast(String value){Toast.makeText(host,value,Toast.LENGTH_SHORT).show();}
    public void back(){close.run();}
}
