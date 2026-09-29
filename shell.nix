{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    (python313.withPackages (ps: with ps; [
      pyqt6
      pyqt6-webengine
      pymupdf
      qtconsole
      ipykernel
    ]))
    libxcb-cursor
    ttyd  # optional: real-terminal Console backend (see console_backend setting)
  ];

  # See projectflow-nix's identical shellHook comment: Qt's xcb platform plugin
  # dlopen()s libxcb-cursor.so.0 at runtime, so it needs to be on LD_LIBRARY_PATH, not
  # just present as a buildInput. Platform selection (prefer xcb, fall back to wayland
  # only when no $DISPLAY is reachable at all) also mirrors projectflow-nix exactly —
  # see that script's own comment for the reasoning.
  shellHook = ''
    export LD_LIBRARY_PATH="$(echo "$NIX_LDFLAGS" | tr ' ' '\n' | sed -n 's/^-L//p' | tr '\n' ':')$LD_LIBRARY_PATH"
    if [ -n "$DISPLAY" ]; then
      export QT_QPA_PLATFORM=xcb
    else
      export QT_QPA_PLATFORM=wayland
    fi
  '';
}
