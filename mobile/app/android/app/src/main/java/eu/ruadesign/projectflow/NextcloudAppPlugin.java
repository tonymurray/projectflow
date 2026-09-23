package eu.ruadesign.projectflow;

import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.net.Uri;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.util.List;

// Best-effort helper backing the experimental "open in Nextcloud app" Settings toggle (see
// getNextcloudFileId()/Launchers.svelte in the JS layer, which builds the file's Nextcloud
// "direct link" — https://{server}/f/{fileid} — from its WebDAV oc:fileid).
//
// An earlier version of this tried an nc:// custom scheme, based on community reports of
// one existing. Confirmed via `adb shell dumpsys package com.nextcloud.client` against a
// real device that this is wrong for the current app: it registers nc:// only for its own
// login/QR flow (nc://login/...), never for opening files. What it DOES register (as a
// verified Android App Link) is the plain https direct-link pattern itself — but relying on
// that as an ordinary implicit intent would mean the actual outcome (Nextcloud app vs. the
// system browser vs. a chooser dialog) depends on the Nextcloud SERVER having published a
// signed .well-known/assetlinks.json for App Link verification, which is a separate,
// server-side prerequisite this client has no control over and can't assume.
//
// Instead, NEXTCLOUD_PACKAGE is targeted explicitly via Intent.setPackage() — this routes
// straight to any activity in that specific package matching the intent, with no
// disambiguation and no dependency on domain verification at all, as long as the app is
// actually installed and has ANY matching intent-filter (which dumpsys confirmed it does,
// for exactly this https .../f/{id} pattern — resolves to FileDisplayActivity).
//
// Real bug found and fixed via a real device (confirmed the intent DOES work — firing it
// directly via `adb shell am start` opened the file straight in the Nextcloud app's own
// editor — while this plugin still reported {opened: false} for the identical intent):
// `Intent.resolveActivity(PackageManager)` is a convenience method that hardcodes
// PackageManager.MATCH_DEFAULT_ONLY internally, meaning it only counts activities whose
// intent-filter declares `category.DEFAULT`. Android App Links like this one typically
// declare only `category.BROWSABLE`, not `DEFAULT`, so that check was silently failing
// every time regardless of setPackage(). Fixed by querying with `pm.queryIntentActivities
// (intent, 0)` instead — no MATCH_DEFAULT_ONLY restriction, appropriate here since
// setPackage() already narrows resolution to one specific app, removing the "don't
// accidentally match an arbitrary non-browsable activity from any installed app" concern
// that flag exists to guard against for genuinely implicit (no package/component) intents.
//
// The one thing that matters regardless of how resolution is done: never let an
// unresolvable/mismatched intent throw ActivityNotFoundException up through Capacitor — the
// JS caller relies on a clean {opened: false} result to fall back to the browser instead,
// which must always work regardless of whether this experimental path does.
@CapacitorPlugin(name = "NextcloudApp")
public class NextcloudAppPlugin extends Plugin {
    private static final String NEXTCLOUD_PACKAGE = "com.nextcloud.client";

    @PluginMethod
    public void openUri(PluginCall call) {
        String uri = call.getString("uri");
        if (uri == null) {
            call.reject("uri required");
            return;
        }

        JSObject result = new JSObject();
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(uri));
            intent.setPackage(NEXTCLOUD_PACKAGE);
            PackageManager pm = getActivity().getPackageManager();
            List<ResolveInfo> matches = pm.queryIntentActivities(intent, 0);
            boolean resolvable = !matches.isEmpty();
            if (resolvable) {
                getActivity().startActivity(intent);
            }
            result.put("opened", resolvable);
        } catch (Exception e) {
            result.put("opened", false);
        }
        call.resolve(result);
    }
}
