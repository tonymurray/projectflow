package eu.ruadesign.projectflow;

import android.content.Intent;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "ShareReceiver")
public class ShareReceiverPlugin extends Plugin {
    private static ShareReceiverPlugin instance;

    @Override
    public void load() {
        instance = this;
    }

    // Called from MainActivity.onNewIntent() when a SEND intent arrives while the app is already running.
    public static void handleNewIntent(Intent intent) {
        if (instance == null) return;
        JSObject data = extract(intent);
        if (data != null) {
            instance.notifyListeners("shareReceived", data);
        }
    }

    @PluginMethod
    public void getSharedData(PluginCall call) {
        Intent intent = getActivity().getIntent();
        JSObject data = extract(intent);

        // Consume the intent so a plain re-open (tapping the app icon, not a fresh
        // share) doesn't keep re-surfacing the same share forever — singleTask means
        // the same Activity/Intent persists across resumes.
        getActivity().setIntent(new Intent(getActivity(), MainActivity.class));

        call.resolve(data != null ? data : new JSObject().put("text", null));
    }

    private static JSObject extract(Intent intent) {
        if (intent == null || !Intent.ACTION_SEND.equals(intent.getAction())) return null;
        String text = intent.getStringExtra(Intent.EXTRA_TEXT);
        if (text == null) return null;
        String subject = intent.getStringExtra(Intent.EXTRA_SUBJECT);
        JSObject data = new JSObject();
        data.put("text", text);
        data.put("subject", subject);
        return data;
    }
}
