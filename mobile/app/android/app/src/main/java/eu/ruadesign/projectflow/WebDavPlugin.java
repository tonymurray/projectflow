package eu.ruadesign.projectflow;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.Network;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.util.Iterator;

import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

@CapacitorPlugin(name = "WebDav")
public class WebDavPlugin extends Plugin {
    private final OkHttpClient client = new OkHttpClient();
    private ConnectivityManager.NetworkCallback networkCallback;

    @Override
    public void load() {
        // client is a single long-lived OkHttpClient for the whole plugin lifetime, with
        // no awareness of network-interface changes by default — its internal connection
        // pool / failed-route cache can stay tied to a now-dead path (e.g. after a
        // wifi<->wifi or wifi<->mobile-data switch) until something forces it to drop
        // those. Evicting the pool whenever the active network changes is the fix —
        // cheap, and doesn't touch the actual request-handling logic below at all.
        ConnectivityManager cm = (ConnectivityManager) getContext()
            .getSystemService(Context.CONNECTIVITY_SERVICE);
        if (cm == null) return;
        networkCallback = new ConnectivityManager.NetworkCallback() {
            @Override
            public void onAvailable(Network network) {
                client.connectionPool().evictAll();
            }
        };
        cm.registerDefaultNetworkCallback(networkCallback);
    }

    @Override
    protected void handleOnDestroy() {
        ConnectivityManager cm = (ConnectivityManager) getContext()
            .getSystemService(Context.CONNECTIVITY_SERVICE);
        if (cm != null && networkCallback != null) {
            cm.unregisterNetworkCallback(networkCallback);
        }
        super.handleOnDestroy();
    }

    @PluginMethod
    public void request(final PluginCall call) {
        final String method = call.getString("method");
        final String url = call.getString("url");
        final JSObject headers = call.getObject("headers", new JSObject());
        final String body = call.getString("body");
        // Base64-encoded binary body (document/image uploads) — kept as a separate param
        // from `body` rather than trying to detect binary-vs-text from one string field,
        // since a plain String can't safely round-trip arbitrary bytes across the JS
        // bridge (JSON/UTF-16 string handling isn't byte-preserving) the way it can for
        // the JSON/markdown bodies `body` already handles fine.
        final String bodyBase64 = call.getString("bodyBase64");

        if (method == null) { call.reject("method required"); return; }
        if (url == null)    { call.reject("url required"); return; }

        new Thread(() -> {
            try {
                Request.Builder reqBuilder = new Request.Builder().url(url);

                Iterator<String> keys = headers.keys();
                while (keys.hasNext()) {
                    String key = keys.next();
                    String val = headers.getString(key);
                    if (val != null) reqBuilder.header(key, val);
                }

                RequestBody reqBody = null;
                if (bodyBase64 != null) {
                    byte[] bytes = android.util.Base64.decode(bodyBase64, android.util.Base64.NO_WRAP);
                    String contentType = headers.has("Content-Type")
                        ? headers.getString("Content-Type") : "application/octet-stream";
                    reqBody = RequestBody.create(bytes, MediaType.parse(contentType));
                } else if (body != null) {
                    reqBody = RequestBody.create(body, MediaType.parse("text/plain; charset=utf-8"));
                } else if ("PUT".equals(method) || "POST".equals(method)) {
                    reqBody = RequestBody.create(new byte[0]);
                }
                reqBuilder.method(method, reqBody);

                try (Response response = client.newCall(reqBuilder.build()).execute()) {
                    String responseData = response.body() != null ? response.body().string() : "";
                    JSObject result = new JSObject();
                    result.put("status", response.code());
                    result.put("data", responseData);
                    call.resolve(result);
                }
            } catch (Exception e) {
                call.reject(e.getMessage() != null ? e.getMessage() : "Request failed");
            }
        }).start();
    }
}
