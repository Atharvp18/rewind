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
}: {
  ref?: Ref<CameraStageHandle>;
  active: boolean;
  granted: boolean;
}) {
  const camera = useRef<CameraView>(null);
  const barcode = useRef<{ data: string; at: number } | null>(null);

  useImperativeHandle(ref, () => ({
    capture: async () => {
      if (!camera.current) return null;
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
        return { uri: img.uri, barcode: b && Date.now() - b.at < BARCODE_FRESH_MS ? b.data : null, discard };
      } catch {
        discard();
        return null;
      }
    },
  }));

  const onBarcode = (r: BarcodeScanningResult) => {
    barcode.current = { data: r.data.replace(/\D/g, ''), at: Date.now() };
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
          barcodeScannerSettings={{ barcodeTypes: ['ean13', 'upc_a', 'upc_e'] }}
          onBarcodeScanned={onBarcode}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  bg: { backgroundColor: '#000000' },
});
