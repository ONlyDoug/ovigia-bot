# Configuração do ambiente para O Vigia Bot
{ pkgs, ... }: {
  # Qual canal do Nixpkgs usar.
  channel = "stable-23.11";

  # Pacotes a instalar no ambiente.
  packages = [
    pkgs.python311
    pkgs.python311Packages.pip
    pkgs.python311Packages.virtualenv
  ];

  # Variáveis de ambiente.
  env = {};

  idx = {
    # Extensões do VS Code a instalar.
    extensions = [
      "ms-python.python"
      "njpwerner.autodocstring"
    ];

    # Comandos de ciclo de vida.
    workspace = {
      # Corre quando o workspace é criado.
      onCreate = {
        install-dependencies = "python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt";
      };
      # Corre sempre que o workspace abre.
      onStart = {
        activate-venv = "source .venv/bin/activate";
      };
    };
  };
}