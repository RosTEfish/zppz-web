import { Box } from "@mui/material";
import { useEventBackgrounds } from "../hooks/useEventBackgrounds";
import { useEventTheme } from "../contexts/EventThemeProvider";

/** 1:1 event square mark from /bg (brand role); falls back to letter Z. */
export default function BrandLogo({
  size = 32,
  borderRadius = 8,
}: {
  size?: number;
  borderRadius?: number | string;
}) {
  const { brandMark } = useEventBackgrounds();
  const { palette } = useEventTheme();
  if (brandMark?.url) {
    return (
      <Box
        component="img"
        src={brandMark.url}
        alt=""
        aria-hidden="true"
        width={size}
        height={size}
        decoding="async"
        sx={{
          width: size,
          height: size,
          flexShrink: 0,
          borderRadius,
          objectFit: "cover",
          boxShadow: "0 2px 6px -2px rgba(13,53,41,0.35)",
        }}
      />
    );
  }
  return (
    <Box
      aria-hidden="true"
      sx={{
        width: size,
        height: size,
        flexShrink: 0,
        borderRadius,
        display: "grid",
        placeItems: "center",
        fontWeight: 700,
        fontSize: size * 0.52,
        color: "#fff",
        background: `linear-gradient(135deg, ${palette.main} 0%, ${palette.dark} 100%)`,
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.28), 0 2px 6px -2px rgba(13,53,41,0.35)",
      }}
    >
      Z
    </Box>
  );
}
