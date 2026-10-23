import os, re, json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plists')
def resolve_plist(model, build):
    if not model or not build or '..' in model or '..' in build: return None
    path = os.path.join(BASE_DIR, model, build, 'patched.plist')
    return path if os.path.exists(path) else None

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        print(f"\n[DEBUG] Nova requisição GET: {self.path}")
        qs = parse_qs(urlparse(self.path).query)
        
        if 'support_query' in qs:
            model = qs.get('model', [''])[0]
            build = qs.get('build', [''])[0]
            print(f"[DEBUG] support_query recebida - Model: {model}, Build: {build}")
            is_supported = resolve_plist(model, build) is not None
            print(f"[DEBUG] Suportado? {is_supported}")
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'supported': is_supported}).encode())
            return
            
        user_agent = self.headers.get('User-Agent', '')
        print(f"[DEBUG] User-Agent: {user_agent}")
        
        m = re.search(r'model/([a-zA-Z0-9,]+)', user_agent)
        b = re.search(r'build/([a-zA-Z0-9]+)', user_agent)
        model_str = m.group(1) if m else None
        build_str = b.group(1) if b else None

        # Fallback: se não estiver no User-Agent, aceita via query string (?model=...&build=...)
        if not model_str and 'model' in qs:
            model_str = qs['model'][0]
        if not build_str and 'build' in qs:
            build_str = qs['build'][0]

        print(f"[DEBUG] Identificado - Model: {model_str}, Build: {build_str}")
        
        path = resolve_plist(model_str, build_str)
        print(f"[DEBUG] Caminho resolvido (plist): {path}")
        
        if path:
            self.send_response(200)
            self.send_header('Content-Description', 'File Transfer')
            self.send_header('Content-Encoding', 'identity')
            self.send_header('Content-Type', 'application/xml')
            self.send_header('Content-Disposition', 'attachment; filename="patched.plist"')
            self.send_header('Content-Length', str(os.path.getsize(path)))
            self.send_header('Cache-Control', 'must-revalidate')
            self.send_header('Pragma', 'public')
            self.end_headers()
            with open(path, 'rb') as f:
                self.wfile.write(f.read())
            print(f"[DEBUG] Resposta 200 OK enviada (XML, {os.path.getsize(path)} bytes)")
            return
            
        print("[DEBUG] Falha ao encontrar caminho ou resolver os dados, retornando 403 Forbidden")
        self.send_response(403)
        self.end_headers()

if __name__ == '__main__':
    print("Servidor local rodando na porta 8080...")
    HTTPServer(('', 8080), Handler).serve_forever()
