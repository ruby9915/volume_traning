# PlantUML용 Graphviz dot 래퍼. PlantUML은 splines=polyline까지만 노출하므로
# 이 래퍼가 dot 입력의 splines=polyline 을 splines=line 으로 바꿔 StarUML Oblique와 같은 한 줄 직선을 만든다.
# 사용: java -jar plantuml.jar -charset UTF-8 -graphvizdot tools\dot-oblique.bat -tpng <file>.puml
#      (.puml 안에 "skinparam linetype polyline"이 있어야 하고, !pragma layout smetana 가 없어야 한다)
import sys, subprocess
REAL = r"C:\Users\U301-8\AppData\Local\Temp\_graphviz\dot.exe"   # 실제 dot.exe 위치 (환경에 맞게 수정)
args = sys.argv[1:]
if not any(a.startswith("-T") for a in args):
    # PlantUML이 실행 파일 확인용으로 부르는 "dot -V": stdin을 닫지 않으므로 절대 읽지 않는다
    sys.exit(subprocess.run([REAL] + args).returncode)
data = sys.stdin.buffer.read()
data = data.replace(b"splines=polyline", b"splines=line").replace(b'splines="polyline"', b'splines="line"')
p = subprocess.run([REAL] + args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
sys.stdout.buffer.write(p.stdout); sys.stderr.buffer.write(p.stderr); sys.exit(p.returncode)
