{
  description = "Vimm's Lair ROM Downloader";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;

        pythonEnv = python.withPackages (
          ps: with ps; [
            httpx
            beautifulsoup4
            lxml
            click
            rich
            python-dotenv
            anyio
            socksio
          ]
        );
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            pythonEnv
            pkgs.aria2
            pkgs.wget
            pkgs.git
          ];

          shellHook = ''
            echo "🎮 Vimm's Lair Downloader dev shell"
            echo "   Python : $(python --version)"
            echo "   aria2c : $(aria2c --version | head -1)"

            # Tambahkan direktori root ke PATH agar wrapper 'vimms' bisa dipanggil langsung
            export PATH="$PWD:$PATH"

            # Set LD_LIBRARY_PATH untuk C-extensions Python (libstdc++.so.6)
            export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib:$LD_LIBRARY_PATH"
          '';
        };
      }
    );
}
