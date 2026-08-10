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
      in
      {
        packages = {
          default = pkgs.python3Packages.callPackage ./package.nix { };
          vimms-lair-downloader = self.packages.${system}.default;
        };

        apps.default = flake-utils.lib.mkApp {
          drv = self.packages.${system}.default;
          name = "vimms";
        };

        devShells.default = pkgs.mkShell {
          inputsFrom = [ self.packages.${system}.default ];
          packages = [
            self.packages.${system}.default
          ];
          buildInputs = with pkgs; [
            git
          ];

          shellHook = ''
            echo "🎮 Vimm's Lair Downloader dev shell"
            echo "   Python : $(python --version)"
            echo "   aria2c : $(aria2c --version | head -1)"

            alias vimms="PYTHONPATH=\"$PWD:\$PYTHONPATH\" python -m vimms_downloader.cli"
            export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib:$LD_LIBRARY_PATH"
          '';
        };
      }
    );
}
