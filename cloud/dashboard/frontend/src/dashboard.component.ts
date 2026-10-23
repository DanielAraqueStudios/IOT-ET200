import { Component, OnInit, OnDestroy } from "@angular/core";
import { CommonModule } from "@angular/common";
import { environment } from "./environment";
import { AuthService } from "./auth.service";
import { LoginComponent } from "./login.component";
import { AdminDeviceComponent } from "./admin-device.component";

interface TagState {
  tag_name: string;
  value: string;
  updated_at: string;
}

@Component({
  selector: "app-dashboard",
  standalone: true,
  imports: [CommonModule, LoginComponent, AdminDeviceComponent],
  template: `
    <app-login *ngIf="!loggedIn" (loggedIn)="onLoggedIn()"></app-login>
    <ng-container *ngIf="loggedIn">
      <h1>PLC State (read-only)</h1>
      <table>
        <thead><tr><th>Tag</th><th>Value</th><th>Updated</th></tr></thead>
        <tbody>
          <tr *ngFor="let row of tags">
            <td>{{ row.tag_name }}</td>
            <td>{{ row.value }}</td>
            <td>{{ row.updated_at }}</td>
          </tr>
        </tbody>
      </table>
      <app-admin-device></app-admin-device>
    </ng-container>
  `,
})
export class DashboardComponent implements OnInit, OnDestroy {
  tags: TagState[] = [];
  loggedIn = false;
  private timer?: ReturnType<typeof setInterval>;

  constructor(private auth: AuthService) {}

  ngOnInit() {
    this.loggedIn = this.auth.isLoggedIn();
    if (this.loggedIn) {
      this.startPolling();
    }
  }

  ngOnDestroy() {
    if (this.timer) clearInterval(this.timer);
  }

  onLoggedIn() {
    this.loggedIn = true;
    this.startPolling();
  }

  private startPolling() {
    this.poll();
    this.timer = setInterval(() => this.poll(), 2000);
  }

  private async poll() {
    const res = await fetch(`${environment.apiUrl}/api/state`, {
      headers: this.auth.authHeader(),
    });
    if (res.status === 401) {
      this.auth.logout();
      this.loggedIn = false;
      if (this.timer) clearInterval(this.timer);
      return;
    }
    this.tags = await res.json();
  }
}
