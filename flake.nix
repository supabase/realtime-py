{
  description = "realtime-py: a Realtime python client.";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { nixpkgs, pyproject-nix, ... }: let
    for-all-systems = f:
      nixpkgs.lib.genAttrs [
        "x86_64-linux"
        "aarch64-darwin"
        "aarch64-linux"
        "x86_64-darwin"
      ] (system: f nixpkgs.legacyPackages.${system});
    project = pyproject-nix.lib.project.loadPyproject {
      projectRoot = ./.;
    };
    dev-tools = pkgs: [
      (pkgs.python3.withPackages (py-pkgs: [
        py-pkgs.python-lsp-server
        py-pkgs.python-lsp-ruff
        py-pkgs.pylsp-mypy
      ]))
      pkgs.supabase-cli
    ];
  in {
    devShells = for-all-systems (pkgs: let
      # override to add top-level packages in nixpkgs as
      # python3.pkgs packages, so that the renderers can find them
      python = pkgs.python3.override {
        packageOverrides = self: super: {
          ruff = self.toPythonModule pkgs.ruff;
          pre-commit = self.toPythonModule pkgs.pre-commit;
        };
      };
      all-dependencies = project.renderers.withPackages {
        inherit python;
        groups = [ "dev" ];
      };
      dependencies = builtins.groupBy (pkg: if python.pkgs.hasPythonModule pkg then "python" else "toplevel") (all-dependencies python);
      pythonEnv = python.buildEnv.override {
        extraLibs = dependencies.python;
      };
    in {
      default = pkgs.mkShell {
        packages = [ pythonEnv ] ++ (dev-tools pkgs) ++ dependencies.toplevel or [];
      };
    });
  };
}
