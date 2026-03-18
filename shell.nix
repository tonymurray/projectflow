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
  ];
}
