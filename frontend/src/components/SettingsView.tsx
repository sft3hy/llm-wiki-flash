import React from 'react';
import { Settings, Moon, Sun, Globe, Shield, Database } from 'lucide-react';

const SettingsView = () => {
  return (
    <div className="max-w-2xl mx-auto py-12 space-y-12">
      <div className="space-y-2">
        <h2 className="text-3xl font-bold tracking-tight">Settings</h2>
        <p className="text-muted-foreground">Manage your wiki configuration and AI preferences.</p>
      </div>

      <div className="grid gap-6">
        <section className="glass p-6 rounded-2xl space-y-6">
          <div className="flex items-center space-x-3 text-primary">
            <Database className="w-5 h-5" />
            <h3 className="font-semibold">Knowledge Base</h3>
          </div>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Auto-Ingestion</p>
                <p className="text-xs text-muted-foreground">Automatically index files added to the raw directory.</p>
              </div>
              <div className="w-10 h-5 bg-primary/20 rounded-full relative">
                <div className="absolute right-1 top-1 w-3 h-3 bg-primary rounded-full"></div>
              </div>
            </div>
          </div>
        </section>

        <section className="glass p-6 rounded-2xl space-y-6">
          <div className="flex items-center space-x-3 text-primary">
            <Shield className="w-5 h-5" />
            <h3 className="font-semibold">Privacy & Security</h3>
          </div>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Local Processing Only</p>
                <p className="text-xs text-muted-foreground">Ensure data never leaves your local machine.</p>
              </div>
              <div className="w-10 h-5 bg-primary rounded-full relative">
                <div className="absolute right-1 top-1 w-3 h-3 bg-primary-foreground rounded-full"></div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default SettingsView;
