package eu.ruadesign.projectflow;

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

    @PluginMethod
    public void request(final PluginCall call) {
        final String method = call.getString("method");
        final String url = call.getString("url");
        final JSObject headers = call.getObject("headers", new JSObject());
        final String body = call.getString("body");

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
                if (body != null) {
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
