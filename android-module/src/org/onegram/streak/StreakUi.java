package org.onegram.streak;

import android.graphics.*;
import android.os.Bundle;
import android.text.*;
import android.text.style.ReplacementSpan;
import android.view.View;
import java.lang.reflect.*;
import java.util.*;
import java.lang.ref.WeakReference;

public final class StreakUi {
    private static StreakEngine engine;
    private static final WeakHashMap<View,Prepared> prepared=new WeakHashMap<>();
    private static final WeakHashMap<View,MessagePrepared> messages=new WeakHashMap<>();
    private static final class MessagePrepared { long peer;StaticLayout original,decorated; }
    private static final class Prepared {
        long peer; int account,count; boolean active; Object original,decorated; WeakReference<Object> target; Field field;
    }
    private static StreakEngine engine(View view){if(engine==null)engine=new StreakEngine(view.getContext().getApplicationContext());return engine;}
    private static Object field(Object object,String name)throws Exception{
        Class<?> type=object.getClass();while(type!=null){try{Field f=type.getDeclaredField(name);f.setAccessible(true);return f.get(object);}catch(NoSuchFieldException ignored){type=type.getSuperclass();}}
        throw new NoSuchFieldException(name);
    }
    public static void preferencesChanged(){
        if(engine!=null){engine.close();engine=null;}
        for(View view:new ArrayList<View>(prepared.keySet())){if(view!=null){restore(view);view.invalidate();}}
    }
    public static void recalculate(int account){
        try{
            if(engine==null)engine=new StreakEngine(org.onegram.ignore.IgnoreStore.context());
            engine.clearOwner(org.onegram.ignore.IgnoreStore.owner(account));
        }catch(Exception error){android.util.Log.e("OneGram","Cannot reset streak cache",error);}
    }
    private static final WeakHashMap<View,String> searchHints=new WeakHashMap<>();
    public static void updateProgress(View root){
        try{
            boolean hint=false;CharSequence text=null;
            if(root instanceof android.widget.EditText){hint=true;text=((android.widget.EditText)root).getHint();try{Object layout=root.getClass().getMethod("getHintLayoutEx").invoke(root);if(layout instanceof Layout)text=((Layout)layout).getText();}catch(Exception ignored){}}
            else if(root instanceof android.widget.TextView)text=((android.widget.TextView)root).getText();
            else try{text=(CharSequence)root.getClass().getMethod("getText").invoke(root);}catch(Exception ignored){}
            String label=text==null?"":text.toString();
            boolean candidate=label.equals("Поиск чатов")||label.equals("Search chats")||(hint&&(label.equals("Поиск")||label.equals("Search")))||label.startsWith("Загрузка ваших серий")||label.startsWith("Загрузка ваших огоньков ")||label.startsWith("Loading your streaks");
            if(candidate){
                if(!label.startsWith("Загрузка")&&!label.startsWith("Loading your"))searchHints.put(root,label);
                int percent=engine==null?-1:engine.progress();String original=searchHints.get(root);if(original==null)original=org.onegram.OneGramUi.russian()?"Поиск чатов":"Search chats";
                String value=percent<0?original:(org.onegram.OneGramUi.russian()?"Загрузка ваших серий… ":"Loading your streaks… ")+percent+"%";
                if(!value.equals(label)){
                    if(hint){try{root.getClass().getMethod("setHintText",CharSequence.class,boolean.class).invoke(root,value,false);}catch(Exception ignored){try{root.getClass().getMethod("setHintText",CharSequence.class).invoke(root,value);}catch(Exception fallback){((android.widget.EditText)root).setHint(value);}}}
                    else if(root instanceof android.widget.TextView)((android.widget.TextView)root).setText(value);
                    else root.getClass().getMethod("setText",CharSequence.class).invoke(root,value);
                    root.invalidate();
                }
            }
        }catch(Exception ignored){}
        if(root instanceof android.view.ViewGroup){android.view.ViewGroup group=(android.view.ViewGroup)root;for(int i=0;i<group.getChildCount();i++)updateProgress(group.getChildAt(i));}
    }
    public static void prepareDialog(View view){
        try{
            long peer=((Number)view.getClass().getMethod("getDialogId").invoke(view)).longValue();
            int account;
            try{account=((Number)field(view,"currentAccount")).intValue();}catch(Exception e){account=((Number)field(view,"E0")).intValue();}
            if(peer<=0){restore(view);return;}
            if(!org.onegram.OneGramConfig.showStreaks(account)){restore(view);return;}
            int count=engine(view).get(account,peer,view);
            boolean active=engine(view).activeToday(account,peer);
            if(count<=0){restore(view);return;}
            Prepared previous=prepared.get(view);
            if(previous!=null && previous.account==account && previous.peer==peer && previous.field!=null && previous.field.get(view)==previous.decorated){
                if(previous.count==count && previous.active==active)return;
                previous.field.set(view,previous.original);
            }
            Field chosen=null;StaticLayout layout=null;
            try{chosen=view.getClass().getDeclaredField("y2");chosen.setAccessible(true);layout=(StaticLayout)chosen.get(view);}catch(Exception ignored){}
            if(layout==null){
            Object controller=Class.forName("org.telegram.messenger.MessagesController").getMethod("getInstance",int.class).invoke(null,account);
            Object user=null;
            for(Method method:controller.getClass().getMethods())if(method.getName().equals("getUser") && method.getParameterTypes().length==1){Class<?> t=method.getParameterTypes()[0];if(t==long.class||t==Long.class){user=method.invoke(controller,peer);break;}}
            if(user==null)return;
            String first=(String)user.getClass().getField("first_name").get(user);
            String last=(String)user.getClass().getField("last_name").get(user);
            String name=((first==null?"":first)+" "+(last==null?"":last)).trim();
            if(name.isEmpty())return;
            for(Class<?> type=view.getClass();type!=null;type=type.getSuperclass())for(Field f:type.getDeclaredFields()){
                if(f.getType()!=StaticLayout.class)continue;f.setAccessible(true);StaticLayout candidate=(StaticLayout)f.get(view);
                if(candidate==null||candidate.getLineCount()!=1)continue;
                String text=candidate.getText().toString().trim();
                if(text.isEmpty()||!(text.startsWith(name)||name.startsWith(text.replace("РІР‚В¦",""))))continue;
                if(layout==null||candidate.getPaint().getTextSize()>layout.getPaint().getTextSize()){chosen=f;layout=candidate;}
            }
            }
            if(layout==null)return;
            CharSequence text=decorate(layout.getText(),layout.getPaint(),layout.getWidth(),count,active);
            StaticLayout replacement=StaticLayout.Builder.obtain(text,0,text.length(),layout.getPaint(),layout.getWidth())
                .setAlignment(layout.getAlignment()).setIncludePad(false).setMaxLines(1).build();
            Prepared state=new Prepared();state.peer=peer;state.account=account;state.count=count;state.active=active;state.field=chosen;state.original=layout;state.decorated=replacement;
            chosen.set(view,replacement);prepared.put(view,state);
        }catch(Exception ignored){}
    }
    public static void prepareHeader(View container){
        try{
            Object owner=null;
            for(Class<?> type=container.getClass();type!=null && owner==null;type=type.getSuperclass())for(Field f:type.getDeclaredFields()){
                if(f.getType().isPrimitive()||f.getType().getName().startsWith("android."))continue;
                f.setAccessible(true);Object candidate=f.get(container);if(candidate==null)continue;
                try{candidate.getClass().getMethod("getCurrentAccount");candidate.getClass().getMethod("getArguments");owner=candidate;break;}catch(NoSuchMethodException ignored){}
            }
            if(owner==null)return;
            org.onegram.OneGramUi.attachChat(owner);
            Bundle args=(Bundle)owner.getClass().getMethod("getArguments").invoke(owner);
            Object id=args==null?null:args.get("user_id");if(!(id instanceof Number))return;
            long peer=((Number)id).longValue();int account=((Number)owner.getClass().getMethod("getCurrentAccount").invoke(owner)).intValue();
            if(!org.onegram.OneGramConfig.showStreaks(account)){restore(container);return;}
            engine(container).focus(account,peer);
            int count=engine(container).get(account,peer,container);
            boolean active=engine(container).activeToday(account,peer);
            Object title=container.getClass().getMethod("getTitleTextView").invoke(container);
            Prepared previous=prepared.get(container);
            CharSequence current=(CharSequence)title.getClass().getMethod("getText").invoke(title);
            if(previous!=null && previous.peer==peer && previous.account==account && previous.count==count && previous.active==active && current instanceof Spanned && ((Spanned)current).getSpans(0,current.length(),Badge.class).length>0)return;
            if(previous!=null && previous.decorated==current){
                if(previous.peer==peer && previous.account==account && previous.count==count && previous.active==active)return;
                current=(CharSequence)previous.original;
            }
            if(count<=0){restore(container);return;}
            Object rawPaint=title.getClass().getMethod("getPaint").invoke(title);
            if(!(rawPaint instanceof TextPaint))return;
            int width=((View)title).getWidth();if(width<=0)return;
            CharSequence decorated=decorate(current,(TextPaint)rawPaint,width,count,active);
            setText(title,decorated);
            Prepared state=new Prepared();state.peer=peer;state.account=account;state.count=count;state.active=active;state.original=current;state.decorated=decorated;state.target=new WeakReference<>(title);
            prepared.put(container,state);
        }catch(Exception ignored){}
    }
    public static void prepareMessage(View view){
        if(org.onegram.OneGramUi.maskDialogPreview(view))return;
        try{
            Field target=view.getClass().getDeclaredField("d3");target.setAccessible(true);
            StaticLayout layout=(StaticLayout)target.get(view);
            long peer=((Number)view.getClass().getMethod("getDialogId").invoke(view)).longValue();
            boolean muted=(Boolean)view.getClass().getMethod("getIsMuted").invoke(view);
            MessagePrepared previous=messages.get(view);
            if(previous!=null&&layout==previous.decorated){
                if(previous.peer==peer&&muted)return;
                target.set(view,previous.original);layout=previous.original;
            }
            messages.remove(view);
            if(!muted||layout==null)return;
            android.graphics.drawable.Drawable icon=(android.graphics.drawable.Drawable)Class.forName("org.telegram.ui.ActionBar.n6").getField("c1").get(null);
            if(icon==null||icon.getIntrinsicWidth()<=0)return;
            int reserve=icon.getIntrinsicWidth()+Math.round(view.getResources().getDisplayMetrics().density*4);
            int width=Math.max(1,layout.getWidth()-reserve);
            CharSequence text=layout.getText();
            StaticLayout replacement=StaticLayout.Builder.obtain(text,0,text.length(),layout.getPaint(),width)
                .setAlignment(layout.getAlignment()).setIncludePad(false).setMaxLines(Math.max(1,layout.getLineCount()))
                .setEllipsize(TextUtils.TruncateAt.END).setEllipsizedWidth(width)
                .setLineSpacing(layout.getSpacingAdd(),layout.getSpacingMultiplier()).build();
            MessagePrepared state=new MessagePrepared();state.peer=peer;state.original=layout;state.decorated=replacement;
            target.set(view,replacement);messages.put(view,state);
        }catch(Exception error){android.util.Log.w("OneGram","Cannot prepare message mute position",error);}
    }
    public static void moveMute(View view){
        try{
            StaticLayout layout=(StaticLayout)field(view,"d3");if(layout==null||layout.getLineCount()==0)return;
            float left=((Number)field(view,"a3")).floatValue(),top=((Number)field(view,"Z2")).floatValue();
            int line=layout.getLineCount()-1;
            float gap=view.getResources().getDisplayMetrics().density*4;
            Class<?> theme=Class.forName("org.telegram.ui.ActionBar.n6");
            for(String name:new String[]{"c1","d1"}){
                android.graphics.drawable.Drawable icon=(android.graphics.drawable.Drawable)theme.getField(name).get(null);
                Rect bounds=new Rect(icon.getBounds());int width=bounds.width(),height=bounds.height();
                if(width<=0||height<=0)continue;
                boolean rtl=layout.getParagraphDirection(line)<0;
                float x=left+(rtl?layout.getLineLeft(line)-gap-width:layout.getLineRight(line)+gap);
                x=Math.max(0,Math.min(x,view.getWidth()-width));
                float y=top+(layout.getLineTop(line)+layout.getLineBottom(line)-height)/2f;
                icon.setBounds(Math.round(x),Math.round(y),Math.round(x)+width,Math.round(y)+height);
            }
        }catch(Exception error){android.util.Log.w("OneGram","Cannot move mute icon",error);}
    }
    private static CharSequence decorate(CharSequence text,TextPaint paint,int width,int count,boolean active){
        text=strip(text);
        Badge badge=new Badge(count,active);int reserved=badge.getSize(paint,"",0,0,null);
        CharSequence shortened=TextUtils.ellipsize(text,paint,Math.max(1,width-reserved),TextUtils.TruncateAt.END);
        SpannableStringBuilder result=new SpannableStringBuilder(shortened);int start=result.length();result.append("\ufffc");result.setSpan(badge,start,start+1,Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);return result;
    }
    private static CharSequence strip(CharSequence text){
        if(!(text instanceof Spanned))return text;
        SpannableStringBuilder clean=new SpannableStringBuilder(text);
        Badge[] badges=clean.getSpans(0,clean.length(),Badge.class);
        for(int i=badges.length-1;i>=0;i--){int start=clean.getSpanStart(badges[i]),end=clean.getSpanEnd(badges[i]);clean.removeSpan(badges[i]);if(start>=0&&end>start)clean.delete(start,end);}
        return clean;
    }
    private static void restore(View view){
        Prepared state=prepared.remove(view);if(state==null)return;
        try{if(state.field!=null && state.field.get(view)==state.decorated)state.field.set(view,state.original);
            else if(state.target!=null && state.target.get()!=null){Object target=state.target.get();CharSequence text=(CharSequence)target.getClass().getMethod("getText").invoke(target);setText(target,strip(text));}
        }catch(Exception ignored){}
    }
    private static void setText(Object view,CharSequence value)throws Exception{
        try{view.getClass().getMethod("setText",CharSequence.class).invoke(view,value);return;}catch(NoSuchMethodException ignored){}
        for(Method method:view.getClass().getDeclaredMethods())if(method.getParameterTypes().length==1&&method.getParameterTypes()[0]==CharSequence.class&&method.getReturnType()==boolean.class){method.setAccessible(true);method.invoke(view,value);return;}
        throw new NoSuchMethodException("Title text setter");
    }
    public static void clear(){
        for(View view:new ArrayList<>(prepared.keySet())){restore(view);view.invalidate();}
        for(View view:new ArrayList<>(messages.keySet())){
            try{MessagePrepared state=messages.get(view);Field target=view.getClass().getDeclaredField("d3");target.setAccessible(true);if(target.get(view)==state.decorated)target.set(view,state.original);view.invalidate();}catch(Exception ignored){}
        }
        messages.clear();if(engine!=null){engine.close();engine=null;}
    }
    private static final class Badge extends ReplacementSpan {
        final int count;final boolean active;Badge(int count,boolean active){this.count=count;this.active=active;}
        public int getSize(Paint paint,CharSequence text,int start,int end,Paint.FontMetricsInt metrics){return (int)Math.ceil(paint.getTextSize()*1.25f+paint.measureText(Integer.toString(count)));}
        public void draw(Canvas canvas,CharSequence text,int start,int end,float x,int top,int baseline,int bottom,Paint original){
            float size=original.getTextSize();int[] colors=StreakRules.colors(count,active);Paint paint=new Paint(original);paint.setAntiAlias(true);
            canvas.save();canvas.translate(x+size*.18f,baseline-size*1.02f);canvas.scale(size/26f,size/26f);
            Path outer=new Path();outer.moveTo(13,0);outer.cubicTo(14,9,24,10,23,19);outer.cubicTo(22,32,1,31,2,18);outer.cubicTo(2,12,8,10,7,5);outer.cubicTo(11,10,12,4,13,0);outer.close();
            paint.setShader(new LinearGradient(0,0,0,28,new int[]{colors[3],colors[2],colors[1],colors[0]},null,Shader.TileMode.CLAMP));canvas.drawPath(outer,paint);
            Path inner=new Path();inner.moveTo(13,13);inner.cubicTo(12,20,7,20,8,25);inner.cubicTo(11,30,19,27,17,23);inner.cubicTo(17,20,14,18,13,13);paint.setShader(null);paint.setColor(colors[0]);canvas.drawPath(inner,paint);canvas.restore();
            paint=new Paint(original);paint.setColor(colors[2]);canvas.drawText(Integer.toString(count),x+size*1.15f,baseline,paint);
        }
    }
}
