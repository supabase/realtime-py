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
      groupsAttrPaths = {"tool.poetry.group" = "dev"; };
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
    devShells = for-all-systems (pkgs: {
      default = let
        python = pkgs.python3;
        arg = project.renderers.withPackages { inherit python; };
        pythonEnv = python.withPackages arg;
      in
        pkgs.mkShell {
          packages = [ pythonEnv ];
          buildInputs = dev-tools pkgs;
        };
    });
  };
}
