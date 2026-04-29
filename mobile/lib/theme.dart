import 'package:flutter/material.dart';

const kBg = Color(0xFF0F172A);
const kSurface = Color(0xFF1E293B);
const kSurface2 = Color(0xFF253347);
const kPrimary = Color(0xFF10B981);
const kPrimaryDark = Color(0xFF059669);
const kTextPrimary = Color(0xFFF8FAFC);
const kTextSecondary = Color(0xFF94A3B8);
const kBorder = Color(0xFF334155);
const kAmber = Color(0xFFF59E0B);
const kBlue = Color(0xFF3B82F6);
const kRed = Color(0xFFEF4444);

ThemeData buildTheme() => ThemeData(
      useMaterial3: true,
      colorScheme: const ColorScheme.dark(
        surface: kBg,
        primary: kPrimary,
        secondary: kBlue,
        error: kRed,
        onSurface: kTextPrimary,
        onPrimary: Colors.white,
      ),
      scaffoldBackgroundColor: kBg,
      fontFamily: 'sans-serif',
      appBarTheme: const AppBarTheme(
        backgroundColor: kBg,
        foregroundColor: kTextPrimary,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          color: kTextPrimary,
          fontSize: 18,
          fontWeight: FontWeight.w700,
        ),
      ),
      cardTheme: CardThemeData(
        color: kSurface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: kBorder, width: 1),
        ),
        margin: EdgeInsets.zero,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: kSurface,
        hintStyle: const TextStyle(color: kTextSecondary),
        labelStyle: const TextStyle(color: kTextSecondary),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: kBorder),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: kBorder),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: kPrimary, width: 2),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: kPrimary,
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          padding: const EdgeInsets.symmetric(vertical: 14),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
          elevation: 0,
        ),
      ),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: kSurface,
        selectedItemColor: kPrimary,
        unselectedItemColor: kTextSecondary,
        showSelectedLabels: true,
        showUnselectedLabels: true,
        type: BottomNavigationBarType.fixed,
        elevation: 0,
      ),
      chipTheme: ChipThemeData(
        backgroundColor: kSurface2,
        labelStyle: const TextStyle(color: kTextSecondary, fontSize: 13),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        side: const BorderSide(color: kBorder),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      ),
      dividerTheme: const DividerThemeData(color: kBorder, thickness: 1),
      textTheme: const TextTheme(
        headlineSmall: TextStyle(color: kTextPrimary, fontWeight: FontWeight.w700),
        titleLarge: TextStyle(color: kTextPrimary, fontWeight: FontWeight.w600),
        titleMedium: TextStyle(color: kTextPrimary, fontWeight: FontWeight.w500),
        bodyLarge: TextStyle(color: kTextPrimary),
        bodyMedium: TextStyle(color: kTextSecondary),
        labelSmall: TextStyle(color: kTextSecondary, fontSize: 11),
      ),
    );
