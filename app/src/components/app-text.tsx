import { Text, type TextProps } from 'react-native';

import { LineHeight, Type, type Palette, type TypeRole } from '@/constants/theme';
import { useA11y } from '@/lib/a11y';

export type AppTextProps = TextProps & {
  kind?: TypeRole;
  color?: keyof Palette;
};

/**
 * All text goes through here so the in-app text size (1.0 to 2.0) and theme
 * apply everywhere. OS font scaling stays on and multiplies on top.
 */
export function AppText({ kind = 'body', color = 'text', style, ...rest }: AppTextProps) {
  const { palette, settings } = useA11y();
  const t = Type[kind];
  const fontSize = Math.round(t.fontSize * settings.textScale);
  return (
    <Text
      {...rest}
      style={[
        {
          color: palette[color] as string,
          fontSize,
          fontWeight: t.fontWeight,
          lineHeight: Math.round(fontSize * LineHeight),
        },
        style,
      ]}
    />
  );
}
