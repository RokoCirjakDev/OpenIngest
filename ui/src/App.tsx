import { useState, useRef } from "react"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible"
import { ChevronDown, Plus } from "lucide-react"

const API_BASE = "http://localhost:8000"

// ─── Doc Ingest Tab ─────────────────────────────────────────────────────────

function DocIngestTab() {
  const fileRef = useRef<HTMLInputElement>(null)
  const [fileName, setFileName] = useState<string | null>(null)
  const [appId, setAppId] = useState("1")
  const [extraInstructions, setExtraInstructions] = useState("")
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [status, setStatus] = useState<string | null>(null)

  async function handleSubmit() {
    const file = fileRef.current?.files?.[0]
    if (!file) {
      setStatus("Please select a file.")
      return
    }
    setStatus(null)
    const form = new FormData()
    form.append("file", file)
    form.append("metadata", JSON.stringify({ app_id: appId }))
    form.append("extra_instructions", extraInstructions)
    try {
      const res = await fetch(`${API_BASE}/upload/doc`, {
        method: "POST",
        body: form,
      })
      const json = await res.json()
      setStatus(JSON.stringify(json))
    } catch (err) {
      setStatus(`Error: ${String(err)}`)
    }
  }

  return (
    <div className="space-y-4 flex flex-col items-center">
      {/* File picker */}
      <div>
        <input
          ref={fileRef}
          type="file"
          className="hidden"
          id="doc-file-input"
          onChange={(e) => setFileName(e.target.files?.[0]?.name ?? null)}
        />
        <Button variant="outline" onClick={() => fileRef.current?.click()}>
          Choose file
        </Button>
        <span className="ml-2 text-sm text-gray-500">
          {fileName ?? "No file selected"}
        </span>
      </div>

      {/* Advanced (collapsed by default) */}
      <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
        <CollapsibleTrigger asChild>
          <button className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors">
            <ChevronDown
              size={14}
              className={`transition-transform ${advancedOpen ? "rotate-180" : ""}`}
            />
            Advanced
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-2">
          <label className="block text-xs text-gray-500 mb-1">
            App ID
          </label>
          <Input
            placeholder="npr. 10"
            value={appId}
            onChange={(e) => setAppId(e.target.value)}
            className="mb-2"
          />
          <label className="block text-xs text-gray-500 mb-1">
            Extra Instructions
          </label>
          <Textarea
            placeholder="Optional instructions…"
            value={extraInstructions}
            onChange={(e) => setExtraInstructions(e.target.value)}
            className="min-h-[80px]"
          />
        </CollapsibleContent>
      </Collapsible>

      <Button onClick={handleSubmit}>Upload</Button>

      {status && (
        <p className="text-xs text-gray-600 break-all">{status}</p>
      )}
    </div>
  )
}

// ─── Manual Ingest Tab ───────────────────────────────────────────────────────

type MetaRow = { id: number; key: string; value: string }

function ManualIngestTab() {
  const [text, setText] = useState("")
  const [rows, setRows] = useState<MetaRow[]>([])
  const [nextId, setNextId] = useState(0)
  const [status, setStatus] = useState<string | null>(null)

  function addRow() {
    setRows((prev) => [...prev, { id: nextId, key: "", value: "" }])
    setNextId((n) => n + 1)
  }

  function updateRow(id: number, field: "key" | "value", val: string) {
    setRows((prev) =>
      prev.map((r) => (r.id === id ? { ...r, [field]: val } : r))
    )
  }

  async function handleSubmit() {
    setStatus(null)
    const metadata: Record<string, string> = {}
    for (const row of rows) {
      if (row.key) metadata[row.key] = row.value
    }
    try {
      const res = await fetch(`${API_BASE}/upload/manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, metadata }),
      })
      const json = await res.json()
      setStatus(JSON.stringify(json))
    } catch (err) {
      setStatus(`Error: ${String(err)}`)
    }
  }

  return (
    <div className="space-y-4 flex flex-col items-center">
      <Textarea
        placeholder="Enter text to ingest…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        className="min-h-[120px]"
      />

      {/* Metadata rows */}
      <div className="space-y-2">
        {rows.map((row) => (
          <div key={row.id} className="flex gap-2">
            <Input
              placeholder="key"
              value={row.key}
              onChange={(e) => updateRow(row.id, "key", e.target.value)}
            />
            <Input
              placeholder="value"
              value={row.value}
              onChange={(e) => updateRow(row.id, "value", e.target.value)}
            />
          </div>
        ))}
        <Button variant="ghost" size="sm" onClick={addRow}>
          <Plus size={14} className="mr-1" />
          Add metadata
        </Button>
      </div>

      <Button onClick={handleSubmit}>Submit</Button>

      {status && (
        <p className="text-xs text-gray-600 break-all">{status}</p>
      )}
    </div>
  )
}

// ─── Root App ────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <div className="min-h-screen bg-white flex flex-col items-center py-12 px-4">
      <h1 className="text-xl font-semibold tracking-tight text-gray-900 mb-8">
        OpenIngest
      </h1>
      <div className="w-full max-w-lg">
        <Tabs defaultValue="doc" className="w-full flex flex-col items-center">
          <TabsList>
            <TabsTrigger value="doc">Doc ingest</TabsTrigger>
            <TabsTrigger value="manual">Manual ingest</TabsTrigger>
          </TabsList>
          <TabsContent value="doc">
            <div className="mt-4">
              <DocIngestTab />
            </div>
          </TabsContent>
          <TabsContent value="manual">
            <div className="mt-4">
              <ManualIngestTab />
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
