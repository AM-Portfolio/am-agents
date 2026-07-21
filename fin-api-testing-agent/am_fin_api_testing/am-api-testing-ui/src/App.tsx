import React, { useState, useEffect } from 'react';
import { 
  Activity, Server, Terminal, CheckCircle2, AlertCircle, Play, Pause, Filter, 
  ShieldCheck, ChevronRight, Settings2, History, Plus, Trash2, Search, 
  ExternalLink, RefreshCw, Send, Copy, Info, AlertTriangle, Code,
  X, Sparkles, ArrowLeft, Check
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';

const BASE_URL = 'http://localhost:8102/api/v1/meta';

const App: React.FC = () => {
  const [services, setServices] = useState<any[]>([]);
  const [logs, setLogs] = useState<any[]>([]);
  const [isTesting, setIsTesting] = useState(false);
  const [activeTab, setActiveTab] = useState('Services');
  const [sessionId] = useState(`session_${Math.random().toString(36).substring(7)}`);
  const scrollRef = React.useRef<HTMLDivElement>(null);

  const [selectedService, setSelectedService] = useState<any>(null);
  const [selectedApi, setSelectedApi] = useState<any>(null);
  const [endpoints, setEndpoints] = useState<any[]>([]);
  const [isFetchingEndpoints, setIsFetchingEndpoints] = useState(false);
  const [testResults, setTestResults] = useState<any[]>([]);
  const [config, setConfig] = useState<any[]>([]);

  useEffect(() => {
    fetchServices();
    fetchConfig();
    
    const es = new EventSource(`${BASE_URL}/events/${sessionId}`);
    es.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.type === 'test_result') {
        setTestResults(prev => [...prev.filter(r => r.op !== data.content.op), data.content]);
      } else if (data.type !== 'heartbeat') {
        setLogs(prev => [...prev, { 
          time: data.time || new Date().toLocaleTimeString(), 
          type: data.type, 
          content: typeof data.content === 'object' ? JSON.stringify(data.content) : data.content,
          url: data.url || null
        }].slice(-100));
      }
    };
    
    return () => es.close();
  }, [sessionId]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const fetchConfig = async () => {
    try {
      const resp = await axios.get(`${BASE_URL}/config`);
      setConfig(resp.data);
    } catch (err) { console.error(err); }
  };

  const saveConfig = async (newConfig: any[]) => {
    try {
      await axios.post(`${BASE_URL}/config`, newConfig);
      setConfig(newConfig);
      fetchServices();
    } catch (err) { console.error(err); }
  };

  const fetchServices = async () => {
    try {
      const resp = await axios.get(`${BASE_URL}/services`);
      setServices(resp.data.map((s: any) => ({ ...s, latency: s.status === 'healthy' ? 45 + Math.random() * 20 : 0 })));
    } catch (err) {
      console.error('Failed to fetch services', err);
    }
  };

  const fetchEndpoints = async (service: any) => {
    setSelectedService(service);
    setIsFetchingEndpoints(true);
    try {
      const resp = await axios.get(`${BASE_URL}/services/${service.name}/apis`);
      setEndpoints(resp.data);
    } catch (err) {
      console.error('Failed to fetch endpoints', err);
    } finally {
      setIsFetchingEndpoints(false);
    }
  };

  const runBatch = async (serviceName: string) => {
    try {
      await axios.post(`${BASE_URL}/batch`, { service: serviceName, sessionId });
      setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), type: 'info', content: `Starting batch test for ${serviceName}...` }]);
    } catch (err) {
      setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), type: 'error', content: `Failed to trigger batch for ${serviceName}` }]);
    }
  };

  const runIndividualTest = async (opId: string, payload: any = null) => {
    try {
      const resp = await axios.post(`${BASE_URL}/test/${opId}?session_id=${sessionId}`, payload);
      setTestResults(prev => [...prev.filter(r => r.op !== opId), { op: opId, result: resp.data }]);
    } catch (err) {
      console.error('Test failed', err);
    }
  };

  const ManualTestModal = ({ api, onClose }: { api: any, onClose: () => void }) => {
    const [payload, setPayload] = useState('{}');
    const [isGenerating, setIsGenerating] = useState(false);

    const generatePayload = async () => {
      setIsGenerating(true);
      try {
        const resp = await axios.get(`${BASE_URL}/test/template/${api.operationId}`);
        setPayload(JSON.stringify(resp.data, null, 2));
      } catch (err) { console.error(err); }
      finally { setIsGenerating(false); }
    };

    return (
      <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/80 backdrop-blur-xl">
        <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="w-full max-w-2xl bg-[#0f0f13] border border-white/10 rounded-[42px] overflow-hidden shadow-2xl">
          <div className="p-8 border-b border-white/5 flex justify-between items-start">
            <div>
              <h2 className="text-2xl font-black text-neonCyan mb-1 uppercase tracking-tight">Manual API Test</h2>
              <p className="text-[10px] text-gray-500 font-mono uppercase tracking-widest">{api.operationId}</p>
            </div>
            <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors">
              <X className="w-6 h-6" />
            </button>
          </div>
          <div className="p-8 space-y-6">
            <div className="flex items-center gap-4 bg-white/5 p-4 rounded-2xl border border-white/5">
              <span className="px-3 py-1 bg-neonCyan/20 text-neonCyan border border-neonCyan/30 rounded-lg text-[10px] font-black uppercase tracking-widest">{api.method}</span>
              <span className="text-xs font-mono text-gray-400">{api.path}</span>
            </div>
            <div>
              <div className="flex justify-between items-center mb-3">
                <label className="text-[10px] font-black text-gray-500 uppercase tracking-[2px]">Payload (JSON)</label>
                <button onClick={generatePayload} disabled={isGenerating} className="flex items-center gap-2 text-[10px] font-black text-neonPurple hover:text-white uppercase tracking-widest">
                  <Sparkles className={`w-3 h-3 ${isGenerating ? 'animate-spin' : ''}`} />
                  {isGenerating ? 'Generating...' : 'AI Generate'}
                </button>
              </div>
              <textarea 
                value={payload} 
                onChange={(e) => setPayload(e.target.value)}
                className="w-full h-64 bg-black/40 border border-white/10 rounded-2xl p-6 font-mono text-sm outline-none focus:border-neonCyan/50 custom-scrollbar"
                spellCheck={false}
              />
            </div>
          </div>
          <div className="p-8 bg-white/5 flex gap-4">
            <button 
              onClick={() => { runIndividualTest(api.operationId, JSON.parse(payload)); onClose(); }}
              className="flex-1 py-4 bg-neonCyan text-black rounded-2xl text-[10px] font-black uppercase tracking-[2px] transition-all shadow-lg shadow-neonCyan/20"
            >
              Execute Request
            </button>
            <button onClick={onClose} className="px-8 py-4 bg-white/5 border border-white/10 rounded-2xl text-[10px] font-black uppercase tracking-[2px]">Cancel</button>
          </div>
        </motion.div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-background text-white flex flex-col font-sans relative">
      <AnimatePresence>
        {selectedApi && <ManualTestModal api={selectedApi} onClose={() => setSelectedApi(null)} />}
      </AnimatePresence>
      
      <nav className="h-16 border-b border-border flex items-center justify-between px-8 bg-card/50 backdrop-blur-md sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-neonCyan/10 rounded-lg">
            <ShieldCheck className="w-6 h-6 text-neonCyan" />
          </div>
          <span className="font-bold text-xl tracking-tight">API TEST COMMAND CENTER</span>
        </div>
        <div className="flex gap-8">
          {['Services', 'Logs', 'Configuration', 'Reports'].map(tab => (
            <button 
              key={tab}
              onClick={() => { setActiveTab(tab); setSelectedService(null); }}
              className={`text-sm font-medium transition-colors hover:text-neonCyan ${activeTab === tab ? 'text-neonCyan' : 'text-gray-400'}`}
            >
              {tab}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-4">
          <div className="text-xs text-gray-400 flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-success animate-pulse" />
            AGENT ONLINE
          </div>
          <div className="w-10 h-10 rounded-full bg-border" />
        </div>
      </nav>

      <main className="flex-1 p-8 grid grid-cols-12 gap-8 container mx-auto">
        <div className="col-span-8 flex flex-col gap-8">
          {activeTab === 'Services' && !selectedService && (
            <>
              <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold flex items-center gap-2">
                  <Server className="w-6 h-6 text-neonCyan" /> Infrastructure Map
                </h2>
                <button 
                  onClick={fetchServices}
                  className="text-sm bg-neonCyan/10 text-neonCyan px-4 py-2 rounded-lg border border-neonCyan/20 hover:bg-neonCyan/20 transition-all flex items-center gap-2"
                >
                  <Activity className="w-4 h-4" /> RE-SCAN ALL
                </button>
              </div>

              <div className="grid grid-cols-2 gap-6">
                {services.map((service, idx) => (
                  <motion.div 
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.1 }}
                    key={service.name} 
                    onClick={() => fetchEndpoints(service)}
                    className="p-6 bg-card border border-border rounded-2xl hover:border-neonCyan/50 transition-all group relative overflow-hidden shadow-2xl cursor-pointer"
                  >
                    <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                      <Server className="w-12 h-12" />
                    </div>
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-bold text-lg">{service.name}</h3>
                      <div className="flex gap-2">
                        <button onClick={(e) => { e.stopPropagation(); setActiveTab('Configuration'); }} className="p-2 bg-white/5 rounded-lg hover:bg-white/10">
                          <Settings2 className="w-4 h-4 text-gray-400" />
                        </button>
                        <div className="p-2 bg-white/5 rounded-lg">
                          <ChevronRight className="w-5 h-5 text-gray-400 group-hover:text-neonCyan transition-colors" />
                        </div>
                      </div>
                    </div>
                    <div className="space-y-3 mb-6">
                      <div className="flex justify-between text-xs text-gray-400">
                        <span>Status</span>
                        <span className={`font-black flex items-center gap-1 ${service.status === 'healthy' ? 'text-success' : 'text-error animate-pulse'}`}>
                          {service.status === 'healthy' ? <CheckCircle2 className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
                          {service.status === 'healthy' ? 'ONLINE' : 'OFFLINE'}
                        </span>
                      </div>
                      <div className="flex justify-between text-xs text-gray-400">
                        <span>Base URL</span>
                        <span className="text-white font-mono opacity-60 truncate max-w-[150px]">{service.url}</span>
                      </div>
                    </div>
                    <div className="flex items-center justify-between pt-4 border-t border-border">
                      <div className="text-[10px] text-gray-500 font-mono italic">
                        {service.endpoints || 0} APIs indexed
                      </div>
                      <button 
                        onClick={(e) => { e.stopPropagation(); runBatch(service.name); }}
                        className="text-[10px] bg-neonCyan/10 text-neonCyan border border-neonCyan/30 px-3 py-1.5 rounded-lg hover:bg-neonCyan hover:text-black transition-all font-black uppercase tracking-widest"
                      >
                        Run Batch
                      </button>
                    </div>
                  </motion.div>
                ))}
              </div>
            </>
          )}

          {activeTab === 'Services' && selectedService && (
            <div className="space-y-6">
              <div className="flex items-center gap-4 bg-white/5 p-6 rounded-[32px] border border-white/5">
                <button onClick={() => setSelectedService(null)} className="w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center hover:bg-neonCyan hover:text-black transition-all">
                  <ArrowLeft className="w-5 h-5" />
                </button>
                <div>
                  <h3 className="text-2xl font-black text-neonCyan uppercase italic tracking-tighter">{selectedService.name}</h3>
                  <p className="text-[10px] text-gray-500 font-mono tracking-[4px] uppercase">{selectedService.url}</p>
                </div>
              </div>

              <div className="grid gap-4">
                {isFetchingEndpoints ? (
                  <div className="py-20 flex flex-col items-center justify-center glass rounded-[38px]">
                    <div className="w-10 h-10 border-4 border-neonCyan/30 border-t-neonCyan rounded-full animate-spin mb-4" />
                    <p className="text-[10px] font-black text-gray-500 uppercase tracking-widest">Parsing Swagger Spec...</p>
                  </div>
                ) : (
                  endpoints.map((api, idx) => {
                    const result = testResults.find(r => r.op === api.operationId);
                    return (
                      <motion.div 
                        key={api.operationId} 
                        initial={{ opacity: 0, x: -20 }} 
                        animate={{ opacity: 1, x: 0 }} 
                        transition={{ delay: idx * 0.05 }}
                        className="bg-card border border-border p-5 rounded-[24px] flex justify-between items-center group hover:border-white/20 transition-all"
                      >
                        <div className="flex items-center gap-6">
                          <div className={`w-12 h-12 rounded-2xl flex items-center justify-center font-black text-[10px] uppercase tracking-tighter ${
                            api.method === 'GET' ? 'bg-success/10 text-success border border-success/20' : 
                            api.method === 'POST' ? 'bg-neonPurple/10 text-neonPurple border border-neonPurple/20' : 
                            'bg-neonCyan/10 text-neonCyan border border-neonCyan/20'
                          }`}>
                            {api.method}
                          </div>
                          <div>
                            <h4 className="font-bold text-sm mb-1">{api.summary || api.operationId}</h4>
                            <p className="text-[10px] font-mono text-gray-500">{api.path}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-4">
                          {result && (
                            <div className={`px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-widest ${result.result.status === 'success' ? 'bg-success/10 text-success' : 'bg-error/10 text-error'}`}>
                              {result.result.status} {result.result.code}
                            </div>
                          )}
                          <button 
                            onClick={() => runIndividualTest(api.operationId)}
                            className="px-4 py-2 bg-neonCyan text-black text-[9px] font-black rounded-xl uppercase transition-all shadow-lg shadow-neonCyan/10"
                          >
                            RUN
                          </button>
                          <button 
                            onClick={() => setSelectedApi(api)}
                            className="w-10 h-10 bg-white/5 border border-white/10 rounded-xl flex items-center justify-center hover:bg-white/10 transition-all"
                          >
                            < LucideIcon name="Settings2" className="w-4 h-4 text-gray-400" />
                          </button>
                        </div>
                      </motion.div>
                    );
                  })
                )}
              </div>
            </div>
          )}

          {activeTab === 'Configuration' && (
            <div className="glass p-8 rounded-[42px] border border-white/10 space-y-8">
              <div className="flex justify-between items-center">
                <div>
                  <h2 className="text-2xl font-black text-neonPurple uppercase tracking-tighter italic">Infrastructure Map</h2>
                  <p className="text-[10px] text-gray-500 font-mono uppercase tracking-[2px]">Orchestrate your microservices environment</p>
                </div>
                <button 
                  onClick={() => saveConfig([...config, { name: 'New Service', url: 'http://localhost:8000', spec_url: '' }])}
                  className="px-6 py-3 bg-neonPurple text-white rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-lg shadow-neonPurple/20"
                >
                  Add Service
                </button>
              </div>
              
              <div className="space-y-4">
                {config.map((s, idx) => (
                  <div key={idx} className="flex gap-4 items-center bg-black/40 p-4 rounded-2xl border border-white/5">
                    <input 
                      value={s.name} 
                      onChange={(e) => {
                        const next = [...config];
                        next[idx].name = e.target.value;
                        setConfig(next);
                      }}
                      className="bg-transparent border-b border-white/10 outline-none p-2 text-xs font-bold w-1/4" 
                    />
                    <input 
                      value={s.url} 
                      onChange={(e) => {
                        const next = [...config];
                        next[idx].url = e.target.value;
                        setConfig(next);
                      }}
                      className="bg-transparent border-b border-white/10 outline-none p-2 text-xs font-mono w-1/3 text-gray-400" 
                    />
                    <input 
                      value={s.spec_url || ''} 
                      placeholder="OpenAPI Spec URL"
                      onChange={(e) => {
                        const next = [...config];
                        next[idx].spec_url = e.target.value;
                        setConfig(next);
                      }}
                      className="bg-transparent border-b border-white/10 outline-none p-2 text-xs font-mono w-1/3 text-neonCyan/50" 
                    />
                    <button 
                      onClick={() => saveConfig(config)}
                      className="p-2 bg-success/10 text-success rounded-lg hover:bg-success hover:text-black transition-all"
                    >
                      <Check className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="col-span-4 flex flex-col gap-8 sticky top-24 h-[calc(100vh-8rem)]">
          <div className="glass rounded-2xl flex-1 flex flex-col overflow-hidden neon-glow-cyan shadow-2xl bg-black/40">
            <div className="p-4 border-b border-white/10 flex justify-between items-center bg-white/5">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-neonCyan" />
                <span className="text-xs font-bold tracking-widest uppercase">Live Agent Console</span>
              </div>
              <button 
                onClick={() => setLogs([])}
                className="text-[8px] px-2 py-1 bg-white/5 hover:bg-white/10 rounded uppercase font-black"
              >
                Clear
              </button>
            </div>
            <div ref={scrollRef} className="flex-1 p-6 font-mono text-[11px] overflow-y-auto space-y-3 custom-scrollbar">
              {logs.map((log, i) => (
                <div key={i} className="flex flex-col gap-1 group border-l border-white/5 pl-3 mb-4">
                  <div className="flex gap-3">
                    <span className="text-gray-600 shrink-0">[{log.time}]</span>
                    <span className={`shrink-0 uppercase text-[8px] font-black px-1.5 py-0.5 rounded leading-none flex items-center ${
                      log.type === 'error' ? 'bg-error/20 text-error' : 
                      log.type === 'success' ? 'bg-success/20 text-success' :
                      log.type === 'thinking' ? 'bg-neonPurple/20 text-neonPurple italic' :
                      'bg-neonCyan/20 text-neonCyan'
                    }`}>{log.type}</span>
                    {log.url && <span className="text-[8px] text-gray-500 truncate max-w-[100px] hover:max-w-full transition-all">{log.url}</span>}
                  </div>
                  <span className="text-gray-300 group-hover:text-white transition-colors break-all leading-relaxed">{log.content}</span>
                </div>
              ))}
            </div>
            <div className="p-4 bg-white/5 border-t border-white/10 flex gap-4">
              <button 
                onClick={() => setIsTesting(!isTesting)}
                className={`flex-1 flex items-center justify-center gap-2 font-bold py-3 rounded-2xl transition-all hover:scale-[1.02] active:scale-[0.98] shadow-lg ${
                  isTesting ? 'bg-error/20 text-error border border-error/30' : 'bg-neonCyan text-black shadow-neonCyan/40'
                }`}
              >
                {isTesting ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                <span className="text-[10px] font-black uppercase tracking-widest">{isTesting ? 'STOP MONITORING' : 'ACTIVATE AGENT'}</span>
              </button>
            </div>
          </div>

          <div className="bg-neonPurple/5 border border-neonPurple/20 rounded-2xl p-6 neon-glow-purple">
            <div className="flex items-center justify-between mb-4">
              <h4 className="text-sm font-bold text-neonPurple uppercase tracking-widest">Autonomous Status</h4>
              <ShieldCheck className="w-5 h-5 text-neonPurple" />
            </div>
            <p className="text-xs text-gray-400 leading-relaxed">
              Agent is currently monitoring <span className="text-white font-bold">{services.length} services</span>. 
              ReAct loop is configured for <span className="text-neonCyan font-bold">Self-Healing</span> on ports 8000-8099.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
};


export default App;
