package org.onegram;
import android.app.Activity;
import android.os.Bundle;
public final class OneGramActivity extends Activity {
    private OneGramScreen screen;
    @Override public void onCreate(Bundle saved){super.onCreate(saved);getWindow().setBackgroundDrawableResource(android.R.color.transparent);screen=new OneGramScreen(this,getIntent().getStringExtra("screen"),getIntent().getIntExtra("account",OneGramUi.selectedAccount()),()->finish());setContentView(screen);getWindow().setStatusBarColor(screen.surfaceColor());getWindow().setNavigationBarColor(screen.surfaceColor());if(screen.lightTheme())getWindow().getDecorView().setSystemUiVisibility(android.view.View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|android.view.View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);}
    @Override protected void onResume(){super.onResume();if(screen!=null)screen.refresh();}
    @Override public void onBackPressed(){if(screen!=null)screen.back();else super.onBackPressed();}
}
