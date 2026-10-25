import { CameraView, type BarcodeScanningResult } from 'expo-camera';
import { File } from 'expo-file-system';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { useImperativeHandle, useRef, type Ref } from 'react';
import { StyleSheet, View } from 'react-native';

const LONGEST_EDGE = 1280;
const JPEG_QUALITY = 0.7;
const BARCODE_FRESH_MS = 5000;

export interface Capture {
  uri: string;
  /** Pixel size of the sent JPEG, to map vision boxes back onto the screen. */
  width: number;
  height: number;
  barcode: string | null;
  /** Deletes every temp file for this capture. Call it as soon as the upload settles. */
  discard: () => void;
}

export interface CameraStageHandle {
  capture: () => Promise<Capture | null>;
}

/**
 * The full-screen live camera behind every frame (wireframe base layer).
 * Captures are compressed to JPEG, longest edge 1280 px, quality 0.7 (tech
 * spec 1.3). expo-camera writes each shot to the app cache; `discard` deletes
 * it and the resized copy right after upload, so frames are never retained.
 */
export function CameraStage({
  ref,
  active,
  granted,
  torch = false,
  onBarcode,
}: {
  ref?: Ref<CameraStageHandle>;
  active: boolean;
  granted: boolean;
  /** The phone's light, turned on after a scan that was too dark to read. */
  torch?: boolean;
  /** Live barcode position on screen (on-device, no network), for the focus corners. */
  onBarcode?: (code: string, bounds: { x: number; y: number; w: number; h: number } | null) => void;
}) {
  const camera = useRef<CameraView>(null);
  const barcode = useRef<{ data: string; at: number } | null>(null);

  useImperativeHandle(ref, () => ({
    capture: async () => {
      if (!camera.current) {
        console.warn('[capture] no camera view (permission off, or the camera is not ready yet)');
        return null;
      }
      const toDelete: string[] = [];
      const discard = () => {
        for (const uri of toDelete) {
          try {
            new File(uri).delete();
          } catch {
            // already gone
          }
        }
      };
      try {
        const shot = await camera.current.takePictureAsync({ quality: JPEG_QUALITY });
        toDelete.push(shot.uri);
        const scale = LONGEST_EDGE / Math.max(shot.width, shot.height);
        const ctx = ImageManipulator.manipulate(shot.uri);
        if (scale < 1) ctx.resize({ width: Math.round(shot.width * scale) });
        const img = await (await ctx.renderAsync()).saveAsync({
          compress: JPEG_QUALITY,
          format: SaveFormat.JPEG,
        });
        toDelete.push(img.uri);
        const b = barcode.current;
        barcode.current = null;
        return {
          uri: img.uri,
          width: img.width,
          height: img.height,
          barcode: b && Date.now() - b.at < BARCODE_FRESH_MS ? b.data : null,
          discard,
        };
      } catch (e) {
        // Logged so a failure on a real phone shows in the Metro terminal.
        console.warn('[capture] failed:', e instanceof Error ? e.message : e);
        discard();
        return null;
      }
    },
  }));

  const handleBarcode = (r: BarcodeScanningResult) => {
    const data = r.data.replace(/\D/g, '');
    barcode.current = { data, at: Date.now() };
    const b = r.bounds;
    onBarcode?.(
      data,
      b && b.size.width > 0 ? { x: b.origin.x, y: b.origin.y, w: b.size.width, h: b.size.height } : null,
    );
  };

  return (
    <View style={[StyleSheet.absoluteFill, styles.bg]} importantForAccessibility="no-hide-descendants">
      {granted ? (
        <CameraView
          ref={camera}
          style={StyleSheet.absoluteFill}
          facing="back"
          active={active}
          animateShutter={false}
          enableTorch={torch}
          barcodeScannerSettings={{ barcodeTypes: ['ean13', 'upc_a', 'upc_e'] }}
          onBarcodeScanned={handleBarcode}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  bg: { backgroundColor: '#000000' },
});
