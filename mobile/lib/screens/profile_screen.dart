import 'package:flutter/material.dart';
import '../theme.dart';
import '../config.dart';
import 'login_screen.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Avatar card
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: kSurface,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: kBorder),
            ),
            child: Row(
              children: [
                Container(
                  width: 60,
                  height: 60,
                  decoration: BoxDecoration(
                    color: kPrimary.withOpacity(0.15),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.person_outline, color: kPrimary, size: 30),
                ),
                const SizedBox(width: 16),
                const Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Document Officer', style: TextStyle(color: kTextPrimary, fontSize: 16, fontWeight: FontWeight.w700)),
                    SizedBox(height: 4),
                    Text('officer@hillingdon.gov.uk', style: TextStyle(color: kTextSecondary, fontSize: 13)),
                    SizedBox(height: 4),
                    Text('Hillingdon Council', style: TextStyle(color: kTextSecondary, fontSize: 12)),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),

          const Text(
            'SETTINGS',
            style: TextStyle(color: kTextSecondary, fontSize: 11, fontWeight: FontWeight.w600, letterSpacing: 1.2),
          ),
          const SizedBox(height: 10),

          _SettingTile(icon: Icons.notifications_outlined, label: 'Notifications', onTap: () {}),
          _SettingTile(icon: Icons.category_outlined, label: 'Default Category', onTap: () {}),
          _SettingTile(icon: Icons.language_outlined, label: 'Language', onTap: () {}),
          _SettingTile(icon: Icons.lock_outline, label: 'Change Password', onTap: () {}),
          const SizedBox(height: 16),

          const Text(
            'BACKEND',
            style: TextStyle(color: kTextSecondary, fontSize: 11, fontWeight: FontWeight.w600, letterSpacing: 1.2),
          ),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: kSurface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: kBorder),
            ),
            child: Row(
              children: [
                const Icon(Icons.cloud_outlined, color: kPrimary, size: 20),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('API Endpoint', style: TextStyle(color: kTextSecondary, fontSize: 12)),
                      Text(kApiBase, style: const TextStyle(color: kTextPrimary, fontSize: 13)),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),

          // Sign out
          OutlinedButton.icon(
            onPressed: () => Navigator.of(context).pushAndRemoveUntil(
              MaterialPageRoute(builder: (_) => const LoginScreen()),
              (_) => false,
            ),
            icon: const Icon(Icons.logout_outlined, size: 18, color: kRed),
            label: const Text('Sign Out', style: TextStyle(color: kRed)),
            style: OutlinedButton.styleFrom(
              side: BorderSide(color: kRed.withOpacity(0.4)),
              minimumSize: const Size(double.infinity, 48),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
          ),
          const SizedBox(height: 24),

          const Center(
            child: Text(
              'ClearDoc v1.0.0\nHillingdon Council × Brunel University\nSynthetic demo data only',
              textAlign: TextAlign.center,
              style: TextStyle(color: kTextSecondary, fontSize: 11, height: 1.7),
            ),
          ),
        ],
      ),
    );
  }
}

class _SettingTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  const _SettingTile({required this.icon, required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        decoration: BoxDecoration(
          color: kSurface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: kBorder),
        ),
        child: Row(
          children: [
            Icon(icon, color: kTextSecondary, size: 20),
            const SizedBox(width: 12),
            Expanded(child: Text(label, style: const TextStyle(color: kTextPrimary, fontSize: 14))),
            const Icon(Icons.chevron_right, color: kTextSecondary, size: 18),
          ],
        ),
      ),
    );
  }
}
