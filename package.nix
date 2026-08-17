{
  lib,
  buildPythonApplication,
  hatchling,
  makeWrapper,
  httpx,
  beautifulsoup4,
  lxml,
  rich,
  click,
  python-dotenv,
  anyio,
  socksio,
  aria2,
  p7zip,
  extract-xiso,
}:

buildPythonApplication {
  pname = "vimms-lair-downloader";
  version = "0.1.0";
  format = "pyproject";

  src = ./.;

  nativeBuildInputs = [
    hatchling
    makeWrapper
  ];

  propagatedBuildInputs = [
    httpx
    beautifulsoup4
    lxml
    rich
    click
    python-dotenv
    anyio
    socksio
  ];

  postInstall = ''
    wrapProgram $out/bin/vimms \
      --prefix PATH : ${lib.makeBinPath [ aria2 p7zip extract-xiso ]}
  '';

  meta = with lib; {
    description = "CLI downloader for Vimm's Lair ROM vault";
    homepage = "https://github.com/XiaoXioe/vimms-lair-downloader";
    license = licenses.mit;
    mainProgram = "vimms";
  };
}
