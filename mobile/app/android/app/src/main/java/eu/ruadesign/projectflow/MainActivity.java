package eu.ruadesign.projectflow;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(android.os.Bundle savedInstanceState) {
        registerPlugin(WebDavPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
