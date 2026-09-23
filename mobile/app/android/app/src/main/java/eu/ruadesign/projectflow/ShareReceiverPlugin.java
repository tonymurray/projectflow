package eu.ruadesign.projectflow;

import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;
import android.util.Base64;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;

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
        JSObject data = extract(intent, instance.getContext());
        if (data != null) {
            instance.notifyListeners("shareReceived", data);
        }
    }

    @PluginMethod
    public void getSharedData(PluginCall call) {
        Intent intent = getActivity().getIntent();
        JSObject data = extract(intent, getContext());

        // Consume the intent so a plain re-open (tapping the app icon, not a fresh
        // share) doesn't keep re-surfacing the same share forever — singleTask means
        // the same Activity/Intent persists across resumes.
        getActivity().setIntent(new Intent(getActivity(), MainActivity.class));

        call.resolve(data != null ? data : new JSObject().put("text", null));
    }

    // Reads the actual bytes of a shared file, given the content:// URI handed back by
    // getSharedData()/the shareReceived event. Deliberately a SEPARATE method from
    // extract() below rather than reading eagerly there: extract() also runs on
    // MainActivity's own onNewIntent() callback (always the main/UI thread, for the
    // app-already-open case), and a full file read there risks an ANR for anything
    // non-trivially sized. @PluginMethod calls, by contrast, run on Capacitor's own
    // background thread pool, so deferring the actual read to here — called explicitly
    // from JS once the user picks a project, not automatically on share arrival — keeps
    // the main thread free regardless of file size.
    @PluginMethod
    public void readSharedFile(PluginCall call) {
        String uriStr = call.getString("uri");
        if (uriStr == null) {
            call.reject("uri required");
            return;
        }
        try {
            Uri uri = Uri.parse(uriStr);
            try (InputStream in = getContext().getContentResolver().openInputStream(uri)) {
                if (in == null) {
                    call.reject("Could not open shared file");
                    return;
                }
                ByteArrayOutputStream buffer = new ByteArrayOutputStream();
                byte[] chunk = new byte[8192];
                int n;
                while ((n = in.read(chunk)) != -1) {
                    buffer.write(chunk, 0, n);
                }
                JSObject result = new JSObject();
                result.put("base64", Base64.encodeToString(buffer.toByteArray(), Base64.NO_WRAP));
                call.resolve(result);
            }
        } catch (Exception e) {
            call.reject(e.getMessage() != null ? e.getMessage() : "Failed to read shared file");
        }
    }

    // Text/link shares (EXTRA_TEXT) are checked first, unchanged from before. A file share
    // (EXTRA_STREAM) only ever arrives when EXTRA_TEXT is absent — Android's ACTION_SEND
    // carries one or the other, never both — so this only does the cheap parts (the URI
    // string itself, plus a lightweight ContentResolver query for a display name) and
    // leaves the actual byte read to readSharedFile() above.
    private static JSObject extract(Intent intent, Context context) {
        if (intent == null || !Intent.ACTION_SEND.equals(intent.getAction())) return null;

        String text = intent.getStringExtra(Intent.EXTRA_TEXT);
        if (text != null) {
            JSObject data = new JSObject();
            data.put("text", text);
            data.put("subject", intent.getStringExtra(Intent.EXTRA_SUBJECT));
            return data;
        }

        Uri stream = intent.getParcelableExtra(Intent.EXTRA_STREAM);
        if (stream != null) {
            JSObject data = new JSObject();
            data.put("fileUri", stream.toString());
            data.put("fileName", queryDisplayName(context, stream));
            data.put("mimeType", intent.getType());
            return data;
        }

        return null;
    }

    private static String queryDisplayName(Context context, Uri uri) {
        try (Cursor cursor = context.getContentResolver().query(uri, null, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int idx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (idx >= 0) return cursor.getString(idx);
            }
        } catch (Exception e) {
            // Best-effort — a missing display name just means the JS side falls back to
            // a generic filename; not worth failing the whole share over.
        }
        return null;
    }
}
