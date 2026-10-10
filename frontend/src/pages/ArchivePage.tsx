import { type ComponentProps, memo, type ReactNode, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  CardMedia,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle as MuiDialogTitle,
  IconButton,
  Paper,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { Archive, Clock3, Download, Library, Music2, Users, X } from "lucide-react";
import { api, formatDuration, type ArchiveChartRead } from "../api/v1";
import { queryKeys } from "../api/queryKeys";
import { ChartPreviewStage } from "../components/ChartPreviewDialog";
import { PageHeader, ResourceState, useApiResource } from "../components/PagePrimitives";

const EMPTY_CHARTS: ArchiveChartRead[] = [];
type GroupMode = "edition" | "designer";

const LEVEL_SURFACES: Record<string, string> = {
  "1": "#E8F2FF",
  "2": "#E8F6ED",
  "3": "#FFF6D6",
  "4": "#FFE9E7",
  "5": "#F1E9FF",
  "6": "#FAF7FF",
  "7": "#FFF0E2",
};

function DialogTitle({ children, sx }: { children: ReactNode; sx?: ComponentProps<typeof MuiDialogTitle>["sx"] }) {
  return <MuiDialogTitle component="div" sx={sx}>{children}</MuiDialogTitle>;
}

function getChartLevelSlot(sourceLevelSlot?: string): string {
  return /(?:lv_)?([1-7])$/i.exec(sourceLevelSlot?.trim() ?? "")?.[1] ?? "";
}

function designerKey(designer: string): string {
  return designer.trim() || "未标注谱师";
}

const ArchiveChartCard = memo(function ArchiveChartCard({
  chart,
  showEdition,
  onOpen,
}: {
  chart: ArchiveChartRead;
  showEdition: boolean;
  onOpen: (chart: ArchiveChartRead) => void;
}) {
  const isJ = chart.lane === "j";
  const isExhibition = chart.lane === "exhibition" || chart.source_submission_type === "exhibition";
  const levelSlot = getChartLevelSlot(chart.source_level_slot);
  const levelSurface = LEVEL_SURFACES[levelSlot] ?? "background.paper";
  const coverUrl = chart.cover_thumb_path || chart.cover_path;
  return (
    <Card
      variant="outlined"
      sx={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        borderWidth: isJ ? 2 : 1,
        borderColor: isJ ? "secondary.main" : "divider",
        contentVisibility: "auto",
        containIntrinsicSize: "380px",
      }}
    >
      <CardActionArea onClick={() => onOpen(chart)} sx={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "stretch" }}>
        {coverUrl ? (
          <CardMedia component="img" height="164" image={coverUrl} alt="" loading="lazy" decoding="async" sx={{ objectFit: "cover", bgcolor: "#E4EAE6" }} />
        ) : (
          <Box sx={{ height: 164, flexShrink: 0, display: "grid", placeItems: "center", bgcolor: "#E4EAE6", color: "text.secondary" }}>
            <Music2 size={38} />
          </Box>
        )}
        <CardContent sx={{ width: "100%", flex: 1, display: "flex", flexDirection: "column", bgcolor: levelSurface, color: "#17211D", "& .MuiTypography-colorTextSecondary": { color: "#45534D" } }}>
          <Typography variant="h3" noWrap title={chart.title}>{chart.title}</Typography>
          <Stack direction="row" spacing={0.75} useFlexGap sx={{ mt: 1, flexWrap: "wrap" }}>
            <Chip size="small" label={chart.level} />
            <Chip size="small" color={isJ ? "secondary" : isExhibition ? "info" : "default"} variant={isJ || isExhibition ? "filled" : "outlined"} label={isJ ? "J 谱" : isExhibition ? "场外" : "普通谱"} />
            {showEdition ? <Chip size="small" variant="outlined" label={chart.event_name} /> : null}
          </Stack>
          <Stack spacing={0.5} sx={{ mt: 1.25, minHeight: 48 }}>
            <Typography variant="body2" color="text.secondary" noWrap title={chart.author}>
              <Box component="span" sx={{ fontWeight: 700 }}>曲师</Box>　{chart.author}
            </Typography>
            <Typography variant="body2" color="text.secondary" noWrap title={chart.designer || "未标注谱师"}>
              <Box component="span" sx={{ fontWeight: 700 }}>谱师</Box>　{chart.designer || "未标注谱师"}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
              <Clock3 size={13} aria-hidden="true" />
              {formatDuration(chart.track_duration_seconds)}
            </Typography>
          </Stack>
        </CardContent>
      </CardActionArea>
    </Card>
  );
});

function ArchiveDetailDialog({
  chart,
  onClose,
}: {
  chart: ArchiveChartRead | null;
  onClose: () => void;
}) {
  const [previewActive, setPreviewActive] = useState(false);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down("sm"));

  if (!chart) return null;

  async function download() {
    setDownloading(true);
    setError("");
    try {
      await api.downloadArchiveChart(chart.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "下载失败");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <Dialog
      open
      onClose={() => { setPreviewActive(false); onClose(); }}
      fullWidth
      maxWidth="lg"
      fullScreen={mobile}
      slotProps={{ paper: { sx: { overflow: "hidden", maxHeight: { sm: "calc(100dvh - 32px)" } } } }}
    >
      <DialogTitle sx={{ px: { xs: 2, sm: 3 }, py: 1.75, borderBottom: 1, borderColor: "divider" }}>
        <Stack direction="row" spacing={2} sx={{ justifyContent: "space-between", alignItems: "center" }}>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="overline" color="primary.main" sx={{ fontWeight: 800, letterSpacing: ".12em" }}>往届谱面</Typography>
            <Typography variant="h2" noWrap title={chart.title}>{chart.title}</Typography>
          </Box>
          <IconButton aria-label="关闭谱面详情" onClick={() => { setPreviewActive(false); onClose(); }}><X size={20} /></IconButton>
        </Stack>
      </DialogTitle>
      <DialogContent sx={{ p: { xs: 0, sm: 3 }, bgcolor: "background.default" }}>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "minmax(0, 1fr) 300px" }, gap: { xs: 0, sm: 3 }, alignItems: "start" }}>
          <ChartPreviewStage
            active={previewActive}
            source="archive"
            sourceId={chart.id}
            title={chart.title}
            coverUrl={chart.cover_path}
            levelLabel={chart.level}
            canPreview={chart.can_preview !== false}
            onActivate={() => setPreviewActive(true)}
            onDownload={download}
          />
          <Stack spacing={1.5} sx={{ p: { xs: 2, sm: 0 } }}>
            <Paper variant="outlined" sx={{ p: 1.5 }}>
              <Stack spacing={0.75}>
                <Typography variant="body2"><Box component="span" sx={{ fontWeight: 700 }}>届次</Box>　{chart.event_name}</Typography>
                <Typography variant="body2"><Box component="span" sx={{ fontWeight: 700 }}>曲师</Box>　{chart.author}</Typography>
                <Typography variant="body2"><Box component="span" sx={{ fontWeight: 700 }}>谱师</Box>　{chart.designer || "未标注谱师"}</Typography>
                <Typography variant="body2"><Box component="span" sx={{ fontWeight: 700 }}>难度</Box>　{chart.level}</Typography>
              </Stack>
            </Paper>
            {error ? <Alert severity="error">{error}</Alert> : null}
            <Button
              variant="contained"
              startIcon={<Download size={17} />}
              disabled={!chart.can_download || downloading}
              onClick={() => void download()}
            >
              {downloading ? "准备下载…" : "下载原始包"}
            </Button>
            {!chart.can_download ? <Typography variant="caption" color="text.secondary">该谱面暂无可用原始包</Typography> : null}
          </Stack>
        </Box>
      </DialogContent>
    </Dialog>
  );
}

export default function ArchivePage() {
  const editions = useApiResource(queryKeys.archive.editions, api.archiveEditions);
  const charts = useApiResource(queryKeys.archive.charts, api.archiveCharts);
  const [mode, setMode] = useState<GroupMode>("edition");
  const [active, setActive] = useState<ArchiveChartRead | null>(null);
  const allCharts = charts.data ?? EMPTY_CHARTS;
  const editionMeta = editions.data ?? [];

  const editionSections = useMemo(() => {
    const order = editionMeta.length
      ? editionMeta.map((item) => item.id)
      : [...new Set(allCharts.map((chart) => chart.event_id))];
    return order
      .map((eventId) => {
        const meta = editionMeta.find((item) => item.id === eventId);
        const items = allCharts.filter((chart) => chart.event_id === eventId);
        if (!items.length) return null;
        return {
          key: `edition-${eventId}`,
          title: meta?.name ?? items[0]?.event_name ?? `届 #${eventId}`,
          meta: `${items.length} 张谱面`,
          charts: items,
        };
      })
      .filter((section): section is NonNullable<typeof section> => Boolean(section));
  }, [allCharts, editionMeta]);

  const designerSections = useMemo(() => {
    const groups = new Map<string, ArchiveChartRead[]>();
    for (const chart of allCharts) {
      const key = designerKey(chart.designer);
      const bucket = groups.get(key);
      if (bucket) bucket.push(chart);
      else groups.set(key, [chart]);
    }
    return [...groups.entries()]
      .sort(([left], [right]) => left.localeCompare(right, "zh-CN"))
      .map(([title, items]) => ({
        key: `designer-${title}`,
        title,
        meta: `${items.length} 张谱面 · ${new Set(items.map((item) => item.event_id)).size} 届`,
        charts: items,
      }));
  }, [allCharts]);

  const sections = mode === "edition" ? editionSections : designerSections;
  const loading = editions.loading || charts.loading;
  const error = editions.error || charts.error;

  return (
    <Stack spacing={3}>
      <PageHeader
        icon={Archive}
        title="往届乐曲一览"
        meta={allCharts.length ? `共 ${allCharts.length} 张谱面 · ${editionMeta.length || editionSections.length} 届` : undefined}
      />
      <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2 } }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ alignItems: { sm: "center" }, justifyContent: "space-between" }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <Library size={18} />
            <Typography variant="h3">分类查看</Typography>
          </Stack>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={mode}
            aria-label="往届分类方式"
            onChange={(_, value: GroupMode | null) => { if (value) setMode(value); }}
          >
            <ToggleButton value="edition"><Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}><Archive size={15} /><span>按届</span></Stack></ToggleButton>
            <ToggleButton value="designer"><Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}><Users size={15} /><span>按谱师</span></Stack></ToggleButton>
          </ToggleButtonGroup>
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1.25 }}>
          浏览已归档届次的谱面；试听与下载使用届末保留的原始包，不包含当届猜谱公开包。
        </Typography>
      </Paper>
      <ResourceState loading={loading} error={error} empty={!allCharts.length ? "暂无往届谱面。管理员在届末「归档并开启新届」后会出现在这里。" : undefined} emptyIcon={Archive} loadingVariant="cards" />
      {sections.map((section) => (
        <Stack key={section.key} spacing={1.5}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "baseline", justifyContent: "space-between" }}>
            <Typography variant="h3">{section.title}</Typography>
            <Typography variant="caption" color="text.secondary">{section.meta}</Typography>
          </Stack>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: "repeat(3, 1fr)", xl: "repeat(4, 1fr)" }, gap: 2 }}>
            {section.charts.map((chart) => (
              <ArchiveChartCard key={chart.id} chart={chart} showEdition={mode === "designer"} onOpen={setActive} />
            ))}
          </Box>
        </Stack>
      ))}
      <ArchiveDetailDialog chart={active} onClose={() => setActive(null)} />
    </Stack>
  );
}
