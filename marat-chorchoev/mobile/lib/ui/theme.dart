import 'package:flutter/material.dart';

/// App-style dark theme shared with the web app: true black background, near-black
/// rounded cards with a hairline border, bold titles, spaced uppercase labels and a
/// single blue accent. Corner radii are deliberately moderate (rounded, not pill).
class AppColors {
  static const black = Color(0xFF000000);
  static const surface = Color(0xFF0E0E11);
  static const surface2 = Color(0xFF16161A);
  static const border = Color(0xFF1C1C21);
  static const borderStrong = Color(0xFF26262C);
  static const text = Color(0xFFFFFFFF);
  static const muted = Color(0xFFA3A3AD);
  static const primary = Color(0xFF3B82F6);
  static const danger = Color(0xFFFF6B5E);
  static const warn = Color(0xFFE5B445);
  static const ok = Color(0xFF4CC27A);
}

const double kCardRadius = 18;
const double kItemRadius = 14;
const double kControlRadius = 12;

ThemeData buildAppTheme() {
  const scheme = ColorScheme.dark(
    primary: AppColors.primary,
    onPrimary: Colors.white,
    secondary: AppColors.primary,
    onSecondary: Colors.white,
    error: AppColors.danger,
    onError: Colors.black,
    surface: AppColors.black,
    onSurface: AppColors.text,
    onSurfaceVariant: AppColors.muted,
    outline: AppColors.borderStrong,
    outlineVariant: AppColors.border,
    surfaceContainerLowest: AppColors.black,
    surfaceContainerLow: AppColors.surface,
    surfaceContainer: AppColors.surface,
    surfaceContainerHigh: AppColors.surface2,
    surfaceContainerHighest: AppColors.surface2,
  );

  final base = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    colorScheme: scheme,
    scaffoldBackgroundColor: AppColors.black,
  );

  final text = base.textTheme.apply(
    bodyColor: AppColors.text,
    displayColor: AppColors.text,
  );

  RoundedRectangleBorder rounded(double radius, {BorderSide? side}) =>
      RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(radius),
        side: side ?? BorderSide.none,
      );

  OutlineInputBorder inputBorder(Color color, {double width = 1}) =>
      OutlineInputBorder(
        borderRadius: BorderRadius.circular(kControlRadius),
        borderSide: BorderSide(color: color, width: width),
      );

  return base.copyWith(
    textTheme: text.copyWith(
      headlineSmall:
          text.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
      titleLarge: text.titleLarge?.copyWith(fontWeight: FontWeight.w800),
      titleMedium: text.titleMedium?.copyWith(fontWeight: FontWeight.w700),
      labelLarge: text.labelLarge?.copyWith(fontWeight: FontWeight.w600),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.black,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(
          fontSize: 24, fontWeight: FontWeight.w800, color: AppColors.text),
    ),
    cardTheme: CardThemeData(
      color: AppColors.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: const EdgeInsets.symmetric(horizontal: 0, vertical: 6),
      clipBehavior: Clip.antiAlias,
      shape: rounded(kCardRadius,
          side: const BorderSide(color: AppColors.border)),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: AppColors.surface,
      surfaceTintColor: Colors.transparent,
      shape: rounded(kCardRadius,
          side: const BorderSide(color: AppColors.borderStrong)),
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: AppColors.surface,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(kCardRadius)),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: AppColors.black,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      indicatorColor: AppColors.primary.withValues(alpha: 0.16),
      iconTheme: WidgetStateProperty.resolveWith((states) => IconThemeData(
            color: states.contains(WidgetState.selected)
                ? AppColors.primary
                : AppColors.text,
          )),
      labelTextStyle: WidgetStateProperty.resolveWith((states) => TextStyle(
            fontSize: 12,
            fontWeight: states.contains(WidgetState.selected)
                ? FontWeight.w700
                : FontWeight.w500,
            color: states.contains(WidgetState.selected)
                ? AppColors.primary
                : AppColors.muted,
          )),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.surface,
      border: inputBorder(AppColors.borderStrong),
      enabledBorder: inputBorder(AppColors.borderStrong),
      focusedBorder: inputBorder(AppColors.primary, width: 2),
      errorBorder: inputBorder(AppColors.danger),
      focusedErrorBorder: inputBorder(AppColors.danger, width: 2),
      labelStyle: const TextStyle(color: AppColors.muted),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.primary,
        foregroundColor: Colors.white,
        shape: rounded(kControlRadius),
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
        minimumSize: const Size(48, 48),
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.primary,
        foregroundColor: Colors.white,
        elevation: 0,
        shape: rounded(kControlRadius),
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
        minimumSize: const Size(48, 48),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.text,
        backgroundColor: AppColors.surface2,
        side: const BorderSide(color: AppColors.borderStrong),
        shape: rounded(kControlRadius),
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
        minimumSize: const Size(48, 48),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: AppColors.primary,
        shape: rounded(kControlRadius),
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: AppColors.surface2,
      side: const BorderSide(color: AppColors.borderStrong),
      shape: rounded(8),
      labelStyle: const TextStyle(color: AppColors.text),
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: AppColors.surface2,
      contentTextStyle: const TextStyle(color: AppColors.text),
      behavior: SnackBarBehavior.floating,
      shape: rounded(kItemRadius,
          side: const BorderSide(color: AppColors.borderStrong)),
    ),
    dividerTheme: const DividerThemeData(color: AppColors.border),
    listTileTheme: ListTileThemeData(
      shape: rounded(kItemRadius),
      iconColor: AppColors.muted,
    ),
  );
}
